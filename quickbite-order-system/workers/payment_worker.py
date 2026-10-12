"""Payment worker: consumes order.created, simulates payment.

Outcomes (controlled by the PAYMENT_FAIL_MODE env var):
- "off" (default):      always succeeds -> publishes order.paid.
- "random":             ~30% of payments fail transiently (retry demo).
- "transient":          every payment fails transiently -> retries, then
                        order.payment.failed + dead-letter queue.
- "permanent":          every payment fails permanently -> order.payment.failed
                        + dead-letter queue, no retries.

Run: python -m workers.payment_worker
"""
import asyncio
import logging
import random
from uuid import uuid4

from app.config import settings
from app.events import ORDER_CREATED, ORDER_PAID, PAYMENT_FAILED, make_event
from app.models import Order
from .base import BaseWorker, PermanentError, TransientError, run_worker

logger = logging.getLogger("quickbite.workers.payment")


class PaymentWorker(BaseWorker):
    queue_name = "payment.queue"
    worker_name = "payment"

    async def handle(self, *, order_id, event_type, payload, db) -> None:
        order = db.get(Order, order_id)
        if order is None:
            # The order row is gone (e.g. database was reset): charging is
            # impossible, so don't retry forever.
            raise PermanentError(f"order {order_id} not found in database")

        await asyncio.sleep(1.5)  # simulate calling a payment gateway
        self._maybe_fail()

        payment_id = f"pay_{uuid4().hex[:8]}"
        order.status = "PAID"
        db.flush()

        await self.publish_event(
            ORDER_PAID, make_event(ORDER_PAID, order_id, payment_id=payment_id)
        )
        logger.info("Payment %s succeeded for %s", payment_id, order_id)

    def _maybe_fail(self) -> None:
        mode = settings.payment_fail_mode
        if mode == "permanent":
            raise PermanentError("simulated card decline")
        if mode == "transient":
            raise TransientError("simulated gateway timeout")
        if mode == "random" and random.random() < 0.3:
            raise TransientError("simulated random gateway timeout")

    async def on_final_failure(self, *, order_id, event_type, payload, db) -> None:
        order = db.get(Order, order_id)
        if order is not None:
            order.status = "PAYMENT_FAILED"
            db.flush()
        await self.publish_event(
            PAYMENT_FAILED,
            make_event(PAYMENT_FAILED, order_id, reason="payment failed permanently"),
        )
        logger.warning("Published %s for %s", PAYMENT_FAILED, order_id)


if __name__ == "__main__":
    run_worker(PaymentWorker())
