# QuickBite — Knowledge Bytes

A compact knowledge base for understanding, running, testing, and presenting the QuickBite Food Delivery Order Processing System.

## Project at a glance
QuickBite is a backend demo built around FastAPI, SQLite, RabbitMQ, Docker Compose, and separate asynchronous worker services. The API accepts an order and returns an order ID quickly; workers process later events such as payment, restaurant confirmation, delivery assignment, and notifications.

## Contents
- `01-project-overview.md` — purpose, features, stack
- `02-architecture-and-event-flow.md` — architecture and lifecycle
- `03-api-reference.md` — endpoints and example order payload
- `04-rabbitmq-and-workers.md` — queues, events, reliability concepts
- `05-run-and-demo-guide.md` — local startup and evaluator demo
- `06-testing-and-observed-results.md` — tests and observed evidence
- `07-evaluator-questions.md` — short viva questions and answers
- `08-submission-checklist.md` — GitHub and assignment deliverables

## Important accuracy note
This knowledge base combines the assignment PDF requirements with the behavior observed during the local demo. It does not claim that every reliability feature has been experimentally verified. Mark any additional test as complete only after you run it and capture evidence.

## Quick links
- API docs: `http://127.0.0.1:8000/docs`
- Health check: `http://127.0.0.1:8000/health`
- RabbitMQ management: `http://localhost:15672`
- Local RabbitMQ demo credentials commonly configured in this project: `guest` / `guest` (do not reuse these credentials on a public deployment).
