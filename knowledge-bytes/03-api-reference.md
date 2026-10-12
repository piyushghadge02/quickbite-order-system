# 03 — API Reference

Open the interactive Swagger UI at `http://127.0.0.1:8000/docs` while the containers are running.

## `GET /health`
Checks application dependencies. Expected healthy response includes:
```json
{
  "status": "healthy",
  "database_connected": true,
  "rabbitmq_connected": true
}
```
Use the actual response from your current run as evidence; if a dependency is unavailable, the status may be `degraded`.

## `POST /orders`
Creates an order. Example request:
```json
{
  "customer_name": "Customer 1",
  "restaurant_id": "REST001",
  "items": [
    {"name": "Chicken Biryani", "quantity": 1, "price": 250},
    {"name": "Mango Lassi", "quantity": 2, "price": 80}
  ]
}
```
Example response shape:
```json
{
  "order_id": "order_example",
  "status": "PENDING",
  "total_amount": 410,
  "message": "Order accepted and queued for processing."
}
```
The example order total is `1 × 250 + 2 × 80 = 410`. The actual generated order ID will differ.

## `GET /orders/{order_id}`
Replace `{order_id}` with the ID returned by `POST /orders`. It returns the saved order, items, total, current status, driver assignment (when available), and timestamps.

## Suggested demo sequence
1. Run `GET /health`.
2. Run `POST /orders` with the example body.
3. Copy the returned order ID.
4. Run `GET /orders/{order_id}` immediately.
5. Run the GET request again after a few seconds to show asynchronous status updates.
