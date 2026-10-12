# 01 — Project Overview

## Name
QuickBite — Scalable Food Delivery Order Processing System

## Problem
A food-delivery API should acknowledge an order quickly. It should not need to wait for every downstream operation—payment processing, restaurant confirmation, delivery assignment, and customer notifications—to finish before responding.

## Solution
The FastAPI service accepts an order, stores it with an initial status, and publishes an event to RabbitMQ. Independent workers consume events and continue the order workflow asynchronously.

## Technology stack
- **Python + FastAPI:** REST API and request validation
- **SQLite:** local order data persistence
- **RabbitMQ:** message broker and queues
- **aio-pika:** asynchronous RabbitMQ client (as referenced in the project)
- **Docker + Docker Compose:** run the API, broker, and workers as containers
- **pytest:** automated tests

## Main components
1. API service
2. RabbitMQ broker and management UI
3. Payment worker
4. Restaurant worker
5. Delivery worker
6. Notification worker
7. Dead-letter queue for messages that repeatedly fail, where configured

## Main outcome
A customer can create an order through the API and retrieve its changing status while workers process the workflow in the background.
