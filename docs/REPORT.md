# QuickBite — Technical Report

How the Scalable Food Delivery Order Processing System works, and why it is
built the way it is. Written for the assignment's "short report" deliverable.

## 1. Why asynchronous processing?

When a customer places an order, only two things must happen *immediately*:
the order must be saved, and the customer must get an answer. Everything else —
charging the card, asking the restaurant, finding a driver, sending updates —
takes seconds and can fail temporarily.

If the API did all of that inside the HTTP request, one slow payment gateway
would make every customer wait, and a traffic spike would exhaust the server's
request threads. Instead, `POST /orders` does the minimum synchronous work
(validate → save as PENDING → publish `order.created` → respond 201, usually in
milliseconds) and the slow work happens later, in background workers, driven
by messages. The HTTP layer stays fast no matter how slow the workers are.

## 2. Queues as shock absorbers

RabbitMQ sits between the API and the workers. If 1,000 orders arrive in a
minute but the payment worker handles 20, the extra messages simply wait in
`payment.queue`. Nothing is lost, nothing times out, and the API never slows
down: the queue absorbs the burst. This is the core scalability argument for
message queues — producers and consumers proceed at their own pace.

Our topology (see `docs/ARCHITECTURE.md`):

- Exchange `quickbite.orders`, type **topic**, durable. Routing keys name the
  event: `order.created`, `order.paid`, `order.payment.failed`,
  `order.confirmed`, `order.driver.assigned`, `order.failed`.
- `payment.queue` ← `order.created`; `restaurant.queue` ← `order.paid`;
  `delivery.queue` ← `order.confirmed`; `notification.queue` ← `order.*`
  (one binding receives every order event).
- `orders.dead-letter.queue` ← dead-letter exchange `quickbite.dlx`.

## 3. Acknowledgements: "tell me when you're done"

Every worker consumes with **manual acknowledgements**. A message is removed
from the queue only when the worker calls `ack()` *after* finishing the work
(`workers/base.py`, `on_message`). If a worker crashes mid-payment, the broker
never got the ack, so the message is redelivered to another worker instance.
No ack = no loss. This is why the demo "kill the notification worker, restart
it, watch it catch up" works: unacked messages simply wait.

## 4. Retries with a bound

Transient failures (a payment gateway timing out) are worth retrying, but an
*infinite* retry loop would wedge the system on a permanently broken message.
Our policy (`workers/base.py`):

1. Each message carries an `x-retry-count` header (starts at 0).
2. On a `TransientError`, if count < `MAX_RETRIES` (default 3), the worker
   waits briefly (1s, 2s, 4s backoff), **republishes** the message with the
   counter incremented, and acks the original (so it isn't redelivered in a
   tight loop).
3. When the counter is exhausted, the message is nacked with `requeue=False`.

Bounded retries mean a poison message is tried exactly MAX_RETRIES + 1 times,
then moved on — never retried forever.

## 5. Dead-letter queue

Every worker queue is declared with `x-dead-letter-exchange: quickbite.dlx`.
A message nacked with `requeue=False` (permanent failure, exhausted retries,
or malformed JSON) is routed by the broker to `orders.dead-letter.queue`
instead of being dropped. Operators can inspect these messages in the
RabbitMQ management UI, fix the cause, and requeue them. The payment worker
also publishes `order.payment.failed` so the rest of the system keeps moving
(the order becomes PAYMENT_FAILED) while the original message is preserved
for forensics.

## 6. Idempotency: safe duplicates

RabbitMQ guarantees *at-least-once* delivery: a message can arrive twice
(worker crashed after processing but before acking, or a retry republish
overlapped a redelivery). Workers must therefore be safe under duplication.

Two layers protect us:

1. **`processed_events` table.** Before handling a message, the worker checks
   for its idempotency key (`<worker>:<order_id>:<event_type>`). If present,
   the message is acked without reprocessing. The key is a primary key, so
   even two racing worker instances can't both record it — the loser's
   transaction rolls back.
2. **Unique constraint on `notifications(order_id, event_type)`.** A second
   insert of the same notification is rejected by the database itself.

The result is *effectively-once* processing: duplicates may arrive, but their
side effects happen once. (True exactly-once is impossible in distributed
systems; idempotent consumers are the standard answer.)

## 7. The outbox-ish safety net in the API

`POST /orders` commits the order to SQLite **before** publishing. If the
broker is down, the order is still saved (status PENDING,
`event_published=False`) and the API logs a loud warning instead of silently
dropping the order. On startup, the API re-publishes `order.created` for any
orders still flagged unpublished. Accepted orders are therefore never
silently lost — the database is the source of truth, the broker is the
delivery mechanism.

## 8. Scaling

Workers are stateless: any number of payment-worker instances can consume
from `payment.queue`, and RabbitMQ round-robins messages between them
(`prefetch_count` keeps the distribution fair — a worker only holds a few
unacked messages at a time). The demo runs
`docker compose up -d --scale payment-worker=3` and shows three workers
sharing the load. Because state lives in SQLite/RabbitMQ rather than in
worker memory, instances can be added or killed at any time.

## 9. What was hard

- **SQLite shared between containers.** Five processes writing one SQLite
  file needs WAL mode and a busy timeout, plus a shared Docker volume —
  otherwise "database is locked" errors appear under load. PostgreSQL would
  remove this concern (noted as future work).
- **Retry without a delay plugin.** Nacking with `requeue=True` redelivers
  instantly in a hot loop; we chose republish-with-counter plus a small
  `asyncio.sleep` backoff — simple, bounded, no broker plugins needed.
- **Duplicate safety across workers.** A single global idempotency key
  collided between workers (payment and notification both "process"
  `order.created`); namespacing the key per worker fixed it.
