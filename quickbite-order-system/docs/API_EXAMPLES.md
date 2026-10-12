# QuickBite — Sample API Requests and Responses

Base URL for the Docker run: `http://127.0.0.1:8000`
(Base URL for the local run is the same.)

## 1. Health check

Request:

```powershell
curl.exe http://127.0.0.1:8000/health
```

Response (everything up):

```json
{
  "status": "healthy",
  "database_connected": true,
  "rabbitmq_connected": true
}
```

Response (broker down — the API still serves, but reports honestly):

```json
{
  "status": "degraded",
  "database_connected": true,
  "rabbitmq_connected": false
}
```

## 2. Create an order

Request:

```powershell
curl.exe --globoff -X POST http://127.0.0.1:8000/orders `
  -H "Content-Type: application/json" `
  -d '{"customer_name": "Amina Khan", "restaurant_id": "rest_123", "items": [{"name": "Chicken Biryani", "quantity": 2, "price": 12.5}, {"name": "Mango Lassi", "quantity": 1, "price": 4.0}]}'
```

Success response — HTTP 201:

```json
{
  "order_id": "order_17ecc114",
  "status": "PENDING",
  "total_amount": 29.0,
  "message": "Order accepted and queued for processing."
}
```

`total_amount` = 2 × 12.5 + 1 × 4.0 = 29.0.

Invalid request (empty items list) — HTTP 422:

```powershell
curl.exe --globoff -X POST http://127.0.0.1:8000/orders `
  -H "Content-Type: application/json" `
  -d '{"customer_name": "Amina Khan", "restaurant_id": "rest_123", "items": []}'
```

```json
{
  "detail": [
    {
      "type": "too_short",
      "loc": ["body", "items"],
      "msg": "List should have at least 1 item after validation, not 0",
      "input": []
    }
  ]
}
```

Other 422 cases: missing/empty `customer_name` or `restaurant_id`,
`quantity` ≤ 0, `price` ≤ 0, wrong data types, missing item `name`.

## 3. Get order status

Request:

```powershell
curl.exe http://127.0.0.1:8000/orders/order_17ecc114
```

Response — HTTP 200 (status moves PENDING → PAID → CONFIRMED → DRIVER_ASSIGNED
as the workers process the order; poll this endpoint to watch it change):

```json
{
  "order_id": "order_17ecc114",
  "customer_name": "Amina Khan",
  "restaurant_id": "rest_123",
  "items": [
    {"name": "Chicken Biryani", "quantity": 2, "price": 12.5},
    {"name": "Mango Lassi", "quantity": 1, "price": 4.0}
  ],
  "total_amount": 29.0,
  "status": "DRIVER_ASSIGNED",
  "driver_id": "driver_482",
  "created_at": "2026-10-12T09:30:00Z",
  "updated_at": "2026-10-12T09:30:12Z"
}
```

Unknown order — HTTP 404:

```powershell
curl.exe http://127.0.0.1:8000/orders/order_nope123
```

```json
{"detail": "Order not found"}
```

## 4. Interactive docs

FastAPI serves Swagger UI at http://127.0.0.1:8000/docs — every endpoint can
be tried from the browser with no curl quoting issues.
