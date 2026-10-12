# 06 — Testing and Observed Results

## Automated tests
During the recorded local session, this command completed successfully:
```powershell
python -m pytest tests -v
```
Observed result: **25 passed in 7.27s**.

The first attempt to run tests inside the API container used `/code/tests`, but that path was not mounted there and pytest reported that the directory did not exist. Running tests from the project folder on Windows succeeded.

## API workflow observed
- `POST /orders` returned HTTP `201` and a generated order ID.
- The response initially used status `PENDING` and reported that the order was queued.
- `GET /orders/{order_id}` returned HTTP `200`.
- Subsequent order reads showed status `DRIVER_ASSIGNED` and a driver ID for example orders.
- The order data contained customer name, restaurant ID, items, total, status, driver ID, and timestamps.
- `/health` later returned `healthy` with both `database_connected` and `rabbitmq_connected` set to `true`.

## Worker evidence observed
Payment worker logs showed successful payment processing and messages such as `Processed payment:order_...:order.created`. Use current logs for the final recording because log timestamps and order IDs change.

## What still needs deliberate evidence
- A stopped notification worker buffering messages and processing them after restart.
- A forced payment failure, retry, and dead-letter queue outcome.
- Scaling comparison between one and multiple payment workers.
- Screenshots or a short recording of the final working run.

A test suite passing does not automatically prove every manual failure/scaling scenario was demonstrated.
