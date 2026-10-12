# QuickBite — Architecture

```
                        ┌──────────────────────────────────────────────────────┐
                        │                      Customer                        │
                        │              (curl / Postman / browser)              │
                        └───────────────┬──────────────────────▲───────────────┘
                                        │ POST /orders         │ 201 + status
                                        ▼                      │ GET /orders/{id}
                        ┌──────────────────────────────────────────────────────┐
                        │              FastAPI Order Service                   │
                        │   validate (Pydantic) → save PENDING (SQLite) →      │
                        │   publish order.created (publisher confirms) → 201    │
                        └───────┬──────────────────────────────────▲───────────┘
                                │                                  │
                    writes      │                                  │ reads
                                ▼                                  │
                        ┌──────────────────┐                       │
                        │      SQLite      │                       │
                        │ orders           │     ┌─────────────────┴────────┐
                        │ notifications    │     │   RabbitMQ               │
                        │ processed_events │     │                          │
                        └──────────────────┘     │  exchange quickbite.     │
                                ▲                │  orders (topic, durable) │
                                │                │                          │
                ┌───────────────┴────┬───────────┴───────┬──────────────────┤
                │ status updates     │                   │                  │
        ┌───────┴────────┐  ┌────────┴────────┐  ┌───────┴────────┐  ┌──────┴───────────┐
        │ payment.queue  │  │restaurant.queue │  │ delivery.queue │  │notification.queue │
        │ order.created  │  │  order.paid     │  │order.confirmed │  │    order.*        │
        └───────┬────────┘  └────────┬────────┘  └───────┬────────┘  └──────┬───────────┘
                ▼                    ▼                   ▼                  ▼
        ┌──────────────┐    ┌─────────────────┐   ┌──────────────┐   ┌──────────────────┐
        │   Payment    │    │   Restaurant    │   │   Delivery   │   │  Notification    │
        │   Worker     │    │    Worker       │   │   Worker     │   │     Worker       │
        │ PENDING→PAID │    │ PAID→CONFIRMED  │   │ CONFIRMED→   │   │ stores + logs    │
        │ emits        │    │ emits           │   │ DRIVER_      │   │ customer msgs    │
        │ order.paid   │    │ order.confirmed │   │ ASSIGNED     │   │ (deduplicated)   │
        └──────┬───────┘    └────────┬────────┘   │ emits order. │   └──────────────────┘
               │  failures          │            │ driver.      │
               ▼                    │            │ assigned     │
        ┌──────────────────────────────────────────────────────────────┐
        │ order.payment.failed ──► order becomes PAYMENT_FAILED         │
        │ nacked (requeue=False) ──► quickbite.dlx ──►                  │
        │                           orders.dead-letter.queue           │
        └──────────────────────────────────────────────────────────────┘
```

The same diagram as a PNG: `docs/architecture.png`.

## Event flow (happy path)

1. `POST /orders` → order saved as **PENDING**, `order.created` published.
2. Payment worker consumes `payment.queue` → simulates payment → order
   **PAID**, publishes `order.paid`.
3. Restaurant worker consumes `restaurant.queue` → order **CONFIRMED**,
   publishes `order.confirmed`.
4. Delivery worker consumes `delivery.queue` → assigns `driver_NNN`, order
   **DRIVER_ASSIGNED**, publishes `order.driver.assigned`.
5. Notification worker (bound with `order.*`) sees every event and stores a
   customer message per (order, event).

## Failure flow

- Transient payment failure → republish with `x-retry-count+1` (max 3,
  1s/2s/4s backoff) → still failing → `order.payment.failed`, order
  **PAYMENT_FAILED**, original message nacked → `orders.dead-letter.queue`.
- Permanent failure (e.g. card declined) → same, without retries.
- Worker crash → no ack → broker redelivers to the next available instance.

## Mermaid version (renders on GitHub)

```mermaid
flowchart LR
    C[Customer] -->|POST /orders| API[FastAPI Order Service]
    API -->|save PENDING| DB[(SQLite)]
    API -->|order.created| EX{{quickbite.orders\ntopic exchange}}
    EX -->|order.created| PQ[payment.queue]
    EX -->|order.paid| RQ[restaurant.queue]
    EX -->|order.confirmed| DQ[delivery.queue]
    EX -->|order.*| NQ[notification.queue]
    PQ --> PW[Payment Worker]
    PW -->|order.paid| EX
    PW -->|nack| DLX{{quickbite.dlx}} --> DLQ[orders.dead-letter.queue]
    RQ --> RW[Restaurant Worker]
    RW -->|order.confirmed| EX
    DQ --> DW[Delivery Worker]
    DW -->|order.driver.assigned| EX
    NQ --> NW[Notification Worker]
    PW & RW & DW -->|status updates| DB
    NW -->|notifications| DB
    API -->|GET /orders/{id}| C
```
