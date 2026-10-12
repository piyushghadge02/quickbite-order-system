# QuickBite — Demo Guide

Step-by-step demonstrations for the assignment: happy path, worker failure,
retry/dead-letter behavior, and scaling. All commands are PowerShell, run from
the project folder, with the Docker stack already up
(`docker compose up -d --build`).

Open the RabbitMQ management dashboard at http://localhost:15672
(username `guest`, password `guest`) — the Queues tab shows messages flowing
in real time.

## Demo 1 — Happy path

1. Create an order and note the returned `order_id`:
   ```powershell
   curl.exe --globoff -X POST http://127.0.0.1:8000/orders -H "Content-Type: application/json" -d '{"customer_name": "Amina Khan", "restaurant_id": "rest_123", "items": [{"name": "Chicken Biryani", "quantity": 2, "price": 12.5}, {"name": "Mango Lassi", "quantity": 1, "price": 4.0}]}'
   ```
2. Watch the status move (poll every couple of seconds):
   ```powershell
   curl.exe http://127.0.0.1:8000/orders/order_<your_id>
   ```
   You will see `PENDING` → `PAID` → `CONFIRMED` → `DRIVER_ASSIGNED`
   (about 4 seconds total: each worker sleeps ~1s to simulate real work).
3. In the dashboard, watch `payment.queue`, `restaurant.queue`,
   `delivery.queue` and `notification.queue` briefly fill and drain.
4. Follow the worker logs in another terminal:
   ```powershell
   docker compose logs -f payment-worker restaurant-worker delivery-worker notification-worker
   ```
   You will see "Payment pay_xxx succeeded", "Restaurant confirmed",
   "Driver driver_xxx assigned", and the customer notifications.

## Demo 2 — Worker failure (no message loss)

1. Stop the notification worker:
   ```powershell
   docker compose stop notification-worker
   ```
2. Create two or three orders (Demo 1, step 1).
3. In the dashboard, `notification.queue` now **grows**: messages wait
   patiently because the queue is durable and nothing was acked.
4. Restart the worker:
   ```powershell
   docker compose start notification-worker
   ```
5. Watch the queued messages get processed (`docker compose logs -f
   notification-worker`). Payment/restaurant/delivery were unaffected the
   whole time — failures are isolated per queue.

## Demo 3 — Retry and dead-letter queue

1. Switch the payment worker to always-fail-transient mode and recreate it:
   ```powershell
   docker compose stop payment-worker
   # edit docker-compose.yml: PAYMENT_FAIL_MODE: "transient" under payment-worker
   docker compose up -d --build payment-worker
   ```
   (Or quicker for a throwaway demo: `docker compose run -e PAYMENT_FAIL_MODE=transient payment-worker` —
   but the compose-file edit persists for the demo.)
2. Create an order. In the logs you will see:
   `Transient failure ... (attempt 1/3) ... Retrying in 1s.` then attempt
   2/3, 3/3 — the message is republished with a growing `x-retry-count`.
3. After the 3rd retry the worker publishes `order.payment.failed`, the order
   becomes `PAYMENT_FAILED`, and the original message is nacked with
   `requeue=False` → the broker routes it to `orders.dead-letter.queue`.
4. Open the dashboard → Queues → `orders.dead-letter.queue`: the failed
   message is there, inspectable, with its headers and body intact.
5. Set `PAYMENT_FAIL_MODE` back to `"off"` and `docker compose up -d --build
   payment-worker` to restore the happy path.

## Demo 4 — Scaling

1. Create several orders quickly (run the Demo 1 curl a few times).
2. Scale the payment worker to 3 instances:
   ```powershell
   docker compose up -d --scale payment-worker=3
   ```
3. Watch `docker compose logs -f payment-worker`: log lines come from
   `payment-worker-1`, `-2`, `-3` — RabbitMQ round-robins the messages
   across instances (fair thanks to the prefetch limit).
4. Scale back down: `docker compose up -d --scale payment-worker=1`.

## Demo 5 — Duplicate safety (idempotency)

1. In the dashboard, open `payment.queue` and publish the *same*
   `order.created` message twice (copy the body from
   `orders.dead-letter.queue` or craft one with the same `order_id`).
   Easier alternative: stop the payment worker mid-processing
   (`docker compose stop payment-worker` right after creating an order) —
   the unacked message is redelivered when it restarts.
2. Observe: the order is charged once (`order.paid` published once), the
   second delivery is logged as "Duplicate ... ignored (already processed)".

## Cleanup

```powershell
docker compose down        # stop everything, keep data volumes
docker compose down -v     # stop everything AND delete all data (fresh start)
```
