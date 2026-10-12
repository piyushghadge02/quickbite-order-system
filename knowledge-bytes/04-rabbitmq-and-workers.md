# 04 — RabbitMQ and Workers

## Queues seen in the local RabbitMQ dashboard
- `payment.queue`
- `restaurant.queue`
- `delivery.queue`
- `notification.queue`
- `orders.dead-letter.queue`

Open `http://localhost:15672` and choose **Queues and Streams**. Local development credentials observed in this setup: `guest` / `guest`.

## Event progression
- `order.created` — new order has been accepted
- `order.paid` — payment succeeded
- `order.payment.failed` — payment failed
- `order.confirmed` — restaurant confirmed the order
- `order.driver.assigned` — driver assigned
- `order.failed` — order failed / requires review, if emitted by the implementation

## Responsibilities
- **Payment worker:** consumes new orders, simulates payment, and emits a payment outcome.
- **Restaurant worker:** handles paid orders and confirms them.
- **Delivery worker:** assigns a driver after restaurant confirmation.
- **Notification worker:** logs or stores customer-facing updates.
- **Dead-letter queue:** retains messages routed there by the configured failure policy.

## Reliability concepts to explain
- Manual acknowledgements help prevent a message from being considered complete before processing succeeds.
- Retries handle temporary failures, within a configured limit.
- Dead-lettering prevents repeatedly failing messages from cycling forever.
- Idempotency prevents duplicate event delivery from causing duplicate business actions.
- Running multiple worker instances can distribute messages across consumers.

Do not claim a particular retry count, exact delay, or guaranteed failure behavior unless confirmed in the project configuration and demonstrated in logs.
