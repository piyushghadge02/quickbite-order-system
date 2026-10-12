"""Notification worker: consumes every order event (binding "order.*").

Stores one customer-facing notification per (order, event) and logs it.
Duplicate deliveries are harmless: the base class skips already-processed
messages, and the database unique constraint drops racing inserts.

Run: python -m workers.notification_worker
"""
import logging

from sqlalchemy.exc import IntegrityError

from app.models import Notification
from .base import BaseWorker, run_worker

logger = logging.getLogger("quickbite.workers.notification")

NOTIFICATION_TEXTS = {
    "order.created": "Your order {order_id} has been received.",
    "order.paid": "Payment successful for your order {order_id}.",
    "order.payment.failed": "Payment failed for your order {order_id}.",
    "order.confirmed": "The restaurant confirmed your order {order_id}.",
    "order.driver.assigned": "A driver has been assigned to your order {order_id}.",
    "order.failed": "Your order {order_id} could not be completed.",
}


class NotificationWorker(BaseWorker):
    queue_name = "notification.queue"
    worker_name = "notification"

    async def handle(self, *, order_id, event_type, payload, db) -> None:
        template = NOTIFICATION_TEXTS.get(
            event_type, "Update for your order {order_id}: " + event_type + "."
        )
        text = template.format(order_id=order_id)
        try:
            db.add(Notification(order_id=order_id, event_type=event_type, message=text))
            db.flush()
        except IntegrityError:
            # Same (order, event) already stored (e.g. two instances raced).
            db.rollback()
            logger.info("Notification for %s:%s already stored; skipping",
                        order_id, event_type)
            return
        # In a real system this is where an SMS/e-mail would be sent.
        logger.info("Notify %s: %s", order_id, text)


if __name__ == "__main__":
    run_worker(NotificationWorker())
