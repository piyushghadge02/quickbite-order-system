"""Delivery worker: consumes order.confirmed, assigns a driver.

Publishes order.driver.assigned and moves the order to DRIVER_ASSIGNED.

Run: python -m workers.delivery_worker
"""
import asyncio
import logging
import random

from app.events import DRIVER_ASSIGNED, make_event
from app.models import Order
from .base import BaseWorker, PermanentError, run_worker

logger = logging.getLogger("quickbite.workers.delivery")


class DeliveryWorker(BaseWorker):
    queue_name = "delivery.queue"
    worker_name = "delivery"

    async def handle(self, *, order_id, event_type, payload, db) -> None:
        order = db.get(Order, order_id)
        if order is None:
            raise PermanentError(f"order {order_id} not found in database")

        await asyncio.sleep(1.0)  # dispatch looks for a nearby driver
        driver_id = f"driver_{random.randint(100, 999)}"
        order.status = "DRIVER_ASSIGNED"
        order.driver_id = driver_id
        db.flush()

        await self.publish_event(
            DRIVER_ASSIGNED,
            make_event(DRIVER_ASSIGNED, order_id, driver_id=driver_id),
        )
        logger.info("Driver %s assigned to %s", driver_id, order_id)


if __name__ == "__main__":
    run_worker(DeliveryWorker())
