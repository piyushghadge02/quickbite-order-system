# QuickBite — Food Delivery Order Processing System

A complete, beginner-friendly backend built with **FastAPI** and **RabbitMQ**,
implementing the college assignment *"Scalable Food Delivery Order Processing
System"*. A customer places an order through a REST API; the order is saved in
SQLite and an `order.created` event is published to RabbitMQ. Four background
workers (payment → restaurant → delivery → notification) then process the order
asynchronously, with retries, a dead-letter queue, and duplicate protection.

**Start here:** `docs/DEMO.md` (demos), `docs/REPORT.md` (how it works),
`docs/API_EXAMPLES.md` (sample requests), `docs/ARCHITECTURE.md` (+
`docs/architecture.png` diagram).

---

## 1. Prerequisites (install once)

| Tool | Why | Get it |
|---|---|---|
| Python 3.10+ | runs the API, workers, tests | [python.org](https://www.python.org/downloads/) — tick **"Add python.exe to PATH"** during install |
| Docker Desktop | runs RabbitMQ + all services with one command | [docker.com](https://www.docker.com/products/docker-desktop/) |
| VS Code | editor + terminals | [code.visualstudio.com](https://code.visualstudio.com/) |

Verify in PowerShell:

```powershell
python --version
docker --version
docker compose version
```

> If `python` is not recognized, reinstall Python with "Add python.exe to PATH"
> checked, or use `py -3` instead of `python` in the commands below.

## 2. Extract and open the project

1. Extract `quickbite-order-system-final.zip` to a folder, e.g.
   `C:\Users\<you>\Desktop\quickbite-order-system`.
2. In VS Code: **File → Open Folder** and pick that folder.

## 3. Create the virtual environment and install dependencies

In a VS Code PowerShell terminal (**Ctrl+`**) inside the project folder:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Your prompt should now show `(.venv)`. If activation is blocked, run once:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

## 4. Configure environment variables (optional)

The Docker setup below works with its built-in defaults — no `.env` needed.
For the local-Python run (section 9), copy the example and adjust:

```powershell
Copy-Item .env.example .env
```

Never commit the real `.env` (it is already in `.gitignore`).

## 5. Start everything with Docker Compose (recommended)

```powershell
docker compose up -d --build
```

This starts 6 containers: `rabbitmq`, `api`, `payment-worker`,
`restaurant-worker`, `delivery-worker`, `notification-worker`. Check they are
up:

```powershell
docker compose ps
```

- API: http://127.0.0.1:8000 — interactive docs at http://127.0.0.1:8000/docs
- RabbitMQ dashboard: http://localhost:15672 (username `guest`, password `guest`)

## 6. Create and retrieve orders (PowerShell)

```powershell
# Health check
curl.exe http://127.0.0.1:8000/health

# Create an order (expect total_amount 29.0)
curl.exe --globoff -X POST http://127.0.0.1:8000/orders -H "Content-Type: application/json" -d '{"customer_name": "Amina Khan", "restaurant_id": "rest_123", "items": [{"name": "Chicken Biryani", "quantity": 2, "price": 12.5}, {"name": "Mango Lassi", "quantity": 1, "price": 4.0}]}'

# Fetch the order (replace with the order_id from the previous response)
curl.exe http://127.0.0.1:8000/orders/order_abc123
```

Poll `GET /orders/{order_id}` and watch the status move
`PENDING → PAID → CONFIRMED → DRIVER_ASSIGNED` (about 4 seconds).
Tip: use `http://127.0.0.1:8000/docs` in the browser to try the endpoints
without any curl quoting issues.

## 7. View worker logs

```powershell
# All services
docker compose logs -f

# One worker
docker compose logs -f payment-worker
```

## 8. Demonstrate retries, dead-letter handling, and scaling

Full step-by-step scripts are in `docs/DEMO.md`. Quick versions:

```powershell
# Worker failure: messages wait safely, then catch up on restart
docker compose stop notification-worker
# ... create a few orders ...
docker compose start notification-worker
docker compose logs -f notification-worker

# Retries + dead-letter: make every payment fail transiently
# 1) edit docker-compose.yml -> payment-worker -> PAYMENT_FAIL_MODE: "transient"
docker compose up -d --build payment-worker
# 2) create an order, watch 3 retries, then order.payment.failed
#    and the message land in orders.dead-letter.queue (dashboard)
# 3) set PAYMENT_FAIL_MODE back to "off" and rebuild to restore

# Scaling: run 3 payment workers sharing the load
docker compose up -d --scale payment-worker=3
docker compose logs -f payment-worker
docker compose up -d --scale payment-worker=1
```

## 9. Local Python run (without Docker for the app)

You still need a RabbitMQ server — the simplest is to run just the broker
in Docker, and the API/workers as plain Python processes:

```powershell
docker compose up -d rabbitmq
# .env already points at localhost:5672 and ./quickbite.db
uvicorn app.main:app --reload
```

In separate terminals (venv activated in each):

```powershell
python -m workers.payment_worker
python -m workers.restaurant_worker
python -m workers.delivery_worker
python -m workers.notification_worker
```

## 10. Run the automated tests

```powershell
.\.venv\Scripts\Activate.ps1
pytest tests/ -q
```

25 tests cover order creation, validation, totals, persistence, the full
worker chain, transient/permanent payment failures, retry limits,
dead-lettering, duplicate protection, notification dedup, malformed messages,
topology declaration, and health checks. They use fake broker objects, so no
RabbitMQ or Docker is needed.

## 11. Stop everything

```powershell
docker compose down       # stop, keep data volumes
docker compose down -v    # stop AND delete all data (fresh start)
```

---

## Project structure

```
quickbite-order-system/
├── app/
│   ├── main.py            # FastAPI app: POST /orders, GET /orders/{id}, GET /health
│   ├── config.py          # settings from environment variables
│   ├── models.py          # SQLAlchemy models: Order, Notification, ProcessedEvent
│   ├── database.py        # SQLite engine (WAL mode), sessions, init_db
│   ├── schemas.py         # Pydantic request/response validation
│   ├── events.py          # routing keys, queue bindings, event builders
│   └── rabbitmq.py        # aio-pika client: topology, publish with confirms
├── workers/
│   ├── base.py            # shared: manual acks, retries, DLQ, idempotency, prefetch
│   ├── payment_worker.py      # order.created -> PAID / PAYMENT_FAILED
│   ├── restaurant_worker.py   # order.paid -> CONFIRMED
│   ├── delivery_worker.py     # order.confirmed -> DRIVER_ASSIGNED
│   └── notification_worker.py # order.* -> stored + logged notifications
├── tests/                 # pytest suite (25 tests, no broker needed)
├── docs/
│   ├── REPORT.md          # technical report: queues, acks, retries, DLQ, ...
│   ├── DEMO.md            # step-by-step demo scripts
│   ├── API_EXAMPLES.md    # sample requests and responses
│   ├── ARCHITECTURE.md    # architecture description + diagram
│   └── architecture.png   # architecture diagram
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── .gitignore
```

## How it works (short version)

1. `POST /orders` validates the body (Pydantic), saves the order in SQLite as
   `PENDING`, publishes `order.created` to the durable topic exchange
   `quickbite.orders` (with publisher confirms), and returns 201 immediately.
2. The payment worker consumes `payment.queue`, simulates the charge, sets the
   order `PAID`, and publishes `order.paid`. Failures are retried up to 3
   times, then the message goes to `orders.dead-letter.queue`.
3. Restaurant and delivery workers advance the order to `CONFIRMED` and
   `DRIVER_ASSIGNED`, publishing the next event each time.
4. The notification worker (bound to `order.*`) stores one customer message
   per event; duplicates are ignored via idempotency keys and a database
   unique constraint.
5. `GET /health` reports database and RabbitMQ connectivity honestly.

Details: `docs/REPORT.md`.

## Troubleshooting

- **"Could not connect to server" from curl** — the API isn't running.
  Start it (Docker: `docker compose up -d`; local: `uvicorn app.main:app --reload`).
- **`curl: (3) bad range specification`** — the `{...}` in JSON confuses curl.
  Add `--globoff`, paste one command at a time, or just use `/docs`.
- **Port 8000 already in use** — stop the other server, or run uvicorn with
  `--port 8001` (then use that port in URLs).
- **`docker compose up` fails on Windows** — make sure Docker Desktop is
  running (whale icon in the tray) and virtualization is enabled.
- **"database is locked"** — you are likely running the API locally *and* in
  Docker against the same file. Use one method at a time.
- **Activate.ps1 blocked** — `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`.
