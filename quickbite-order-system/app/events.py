"""Routing keys, queue bindings, and event message builders.

Exchange: quickbite.orders (topic, durable) — see the assignment, section 7.
"""
from .config import settings

EXCHANGE_NAME = settings.exchange_name

# Routing keys (assignment section 7.2).
ORDER_CREATED = "order.created"
ORDER_PAID = "order.paid"
PAYMENT_FAILED = "order.payment.failed"
ORDER_CONFIRMED = "order.confirmed"
DRIVER_ASSIGNED = "order.driver.assigned"
ORDER_FAILED = "order.failed"

# Queue -> routing keys it is bound to (assignment section 7.3).
# The notification queue uses "order.*" so it receives every order event.
QUEUES: dict[str, list[str]] = {
    "payment.queue": [ORDER_CREATED],
    "restaurant.queue": [ORDER_PAID],
    "delivery.queue": [ORDER_CONFIRMED],
    "notification.queue": ["order.*"],
}


def idempotency_key(order_id: str, event_type: str) -> str:
    """Unique key per (order, event), e.g. "order_abc123:order.created"."""
    return f"{order_id}:{event_type}"


def make_event(event_type: str, order_id: str, **extra) -> dict:
    """Build a JSON-serializable event message (assignment section 9)."""
    return {
        "event_type": event_type,
        "order_id": order_id,
        "idempotency_key": idempotency_key(order_id, event_type),
        **extra,
    }
