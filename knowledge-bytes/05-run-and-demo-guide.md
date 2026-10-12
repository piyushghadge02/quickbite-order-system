# 05 — Local Run and Evaluator Demo

## Start the system
In VS Code, open a terminal in the folder containing `docker-compose.yml`:
`C:\\Users\\piyus\\OneDrive\\Desktop\\quickbite-order-system-final\\quickbite-order-system`

Run:
```powershell
docker compose up -d --build
docker compose ps
```

Wait until RabbitMQ reports healthy and the services are running.

## Open the interfaces
- Swagger/API: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/health`
- RabbitMQ dashboard: `http://localhost:15672`

## Demo 1 — Happy path (recommended)
1. Show `docker compose ps` to establish that the services are running.
2. Show `GET /health` returning healthy.
3. In Swagger, execute `POST /orders` with the example request in `03-api-reference.md`.
4. Explain that the API returns `PENDING` quickly because later work is asynchronous.
5. Copy the order ID and execute `GET /orders/{order_id}`.
6. Execute GET again after a few seconds; show the later status and driver ID if the workflow completes.
7. Open RabbitMQ dashboard and point out the named queues.
8. Show worker logs:
```powershell
docker compose logs --since 5m payment-worker restaurant-worker delivery-worker notification-worker
```

## Demo 2 — Worker logs and scaling
Only demonstrate this after the happy path works.
1. Show recent worker logs:
```powershell
docker compose logs --since 5m payment-worker
```
2. Start a second payment worker instance:
```powershell
docker compose up -d --scale payment-worker=2 payment-worker
```
3. Submit several orders through Swagger.
4. Show logs from both payment worker replicas:
```powershell
docker compose logs --since 5m payment-worker
```
5. Explain that replicas compete for messages on the same queue. Show evidence from logs rather than assuming equal distribution.

## Optional failure demonstration
The assignment asks for worker-failure and retry/DLQ demonstrations. Perform these only if comfortable restoring the service:
- Stop notification worker, submit orders, inspect queue depth, restart worker, then show processing resumes.
- If the code has a controllable payment failure mode, trigger it and show retry/DLQ behavior.
Do not invent a failure trigger. Inspect the code/configuration first.

## Stop after the demo
```powershell
docker compose down
```
This stops/removes containers and network but normally retains named volumes. Do not add `-v` unless you intentionally want to remove volumes and understand the data-loss impact.
