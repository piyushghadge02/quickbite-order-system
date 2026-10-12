"""Restaurant worker: consumes order.paid, simulates restaurant confirmation.

Publishes order.confirmed and moves the order to CONFIRMED.

Run: python -m workers.restaurant_worker
"""
import asyncio
import logging

from app.events import ORDER_CONFIRMED, make_event
from app.models import Order
from .base import BaseWorker, PermanentError, run_worker

logger = logging.getLogger("quickbite.workers.restaurant")


class RestaurantWorker(BaseWorker):
    queue_name = "restaurant.queue"
    worker_name = "restaurant"

    async def handle(self, *, order_id, event_type, payload, db) -> None:
        order = db.get(Order, order_id)
        if order is None:
            raise PermanentError(f"order {order_id} not found in database")

        await asyncio.sleep(1.0)  # the kitchen takes the ticket
        order.status = "CONFIRMED"
        db.flush()

        await self.publish_event(
            ORDER_CONFIRMED, make_event(ORDER_CONFIRMED, order_id)
        )
        logger.info("Restaurant confirmed %s", order_id)


if __name__ == "__main__":
    run_worker(RestaurantWorker())
