"""Shared worker machinery.

Every worker subclasses BaseWorker, sets `queue_name`, and implements
`handle()`. The base class provides:

- manual acknowledgements (a message is acked only after it was processed),
- bounded retries for transient failures (republish with a retry counter),
- dead-lettering for permanent failures or exhausted retries,
- idempotency: a message is never processed twice (processed_events table),
- prefetch limit so a worker never holds too many unacked messages.

on_message() only needs a message-like object with .body, .headers,
.routing_key, .ack() and .nack(requeue=...), so tests can use a fake.
"""
import asyncio
import json
import logging
import sys

import aio_pika
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.database import SessionLocal, init_db
from app.events import idempotency_key
from app.models import ProcessedEvent
from app.rabbitmq import declare_topology

logger = logging.getLogger("quickbite.workers")


class TransientError(Exception):
    """Temporary problem (e.g. payment gateway timeout): safe to retry."""


class PermanentError(Exception):
    """Will never succeed on retry (e.g. card declined): dead-letter it."""


class BaseWorker:
    queue_name: str = ""
    worker_name: str = "base"

    def __init__(self, session_factory=SessionLocal):
        self.session_factory = session_factory
        self.connection = None
        self.channel = None
        self.exchange = None

    # -- implemented by each worker --------------------------------------
    async def handle(self, *, order_id: str, event_type: str, payload: dict, db) -> None:
        """Do the real work. Raise TransientError/PermanentError on failure.

        Convention: raise *before* writing anything to the database, so a
        failed attempt never leaves a half-written row behind.
        """
        raise NotImplementedError

    async def on_final_failure(self, *, order_id: str, event_type: str, payload: dict, db) -> None:
        """Called when a message will NOT be retried (it goes to the DLQ)."""

    # -- plumbing ----------------------------------------------------------
    async def publish_event(self, routing_key: str, payload: dict) -> None:
        message = aio_pika.Message(
            body=json.dumps(payload).encode("utf-8"),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            content_type="application/json",
        )
        await self.exchange.publish(message, routing_key=routing_key)

    async def on_message(self, message) -> None:
        try:
            payload = json.loads(message.body.decode("utf-8"))
        except Exception:
            logger.warning("Dropping malformed message (not JSON)")
            await message.nack(requeue=False)  # poison -> dead-letter queue
            return

        event_type = payload.get("event_type") or message.routing_key
        order_id = payload.get("order_id", "unknown")
        # Namespaced per worker: the payment worker and the notification worker
        # can each process "the same" event without clashing.
        key = f"{self.worker_name}:{idempotency_key(order_id, event_type)}"

        db = self.session_factory()
        try:
            if db.get(ProcessedEvent, key) is not None:
                logger.info("Duplicate %s ignored (already processed)", key)
                await message.ack()
                return

            try:
                await self.handle(order_id=order_id, event_type=event_type,
                                  payload=payload, db=db)
            except TransientError as exc:
                await self._retry_or_dead(message, key, order_id, event_type,
                                          payload, db, exc)
                return
            except PermanentError as exc:
                logger.warning("Permanent failure for %s: %s", key, exc)
                await self._dead_letter(message, key, order_id, event_type, payload, db)
                return
            except Exception:
                # Unexpected bug: bounded retry, never an infinite poison loop.
                logger.exception("Unexpected error for %s", key)
                await self._retry_or_dead(message, key, order_id, event_type,
                                          payload, db, RuntimeError("unexpected error"))
                return

            self._mark_processed(db, key)
            db.commit()
            await message.ack()
            logger.info("Processed %s", key)
        finally:
            db.close()

    async def _retry_or_dead(self, message, key, order_id, event_type, payload, db, exc):
        db.rollback()  # discard any partial state from the failed attempt
        retries = int((message.headers or {}).get("x-retry-count", 0))
        if retries < settings.max_retries:
            # Simple bounded backoff: 1s, 2s, 4s, ... (capped at 8s).
            wait = min(2 ** retries, 8)
            logger.warning("Transient failure for %s (attempt %d/%d): %s. Retrying in %ss.",
                           key, retries + 1, settings.max_retries, exc, wait)
            await asyncio.sleep(wait)
            headers = dict(message.headers or {})
            headers["x-retry-count"] = retries + 1
            # Republish with the bumped counter, then ack the original so it
            # is not redelivered immediately in a tight loop.
            await self.exchange.publish(
                aio_pika.Message(
                    body=message.body,
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    headers=headers,
                    content_type="application/json",
                ),
                routing_key=message.routing_key,
            )
            await message.ack()
        else:
            logger.warning("Retry limit reached for %s; dead-lettering", key)
            await self._dead_letter(message, key, order_id, event_type, payload, db)

    async def _dead_letter(self, message, key, order_id, event_type, payload, db):
        db.rollback()  # discard any partial state from the failed attempt
        try:
            await self.on_final_failure(order_id=order_id, event_type=event_type,
                                        payload=payload, db=db)
            self._mark_processed(db, key)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("on_final_failure crashed for %s", key)
        # requeue=False + x-dead-letter-exchange on the queue -> the broker
        # routes this message to orders.dead-letter.queue.
        await message.nack(requeue=False)

    def _mark_processed(self, db, key: str) -> None:
        try:
            db.add(ProcessedEvent(idempotency_key=key, worker=self.worker_name))
            db.flush()
        except IntegrityError:
            # Another worker instance processed it first; our work (if any)
            # is rolled back with it, so nothing is applied twice.
            db.rollback()

    async def run(self) -> None:
        init_db()
        try:
            # Bounded initial wait: a down broker must not hang startup
            # forever. Docker's restart policy retries; local users get a
            # clear error instead of silence.
            self.connection = await asyncio.wait_for(
                aio_pika.connect_robust(settings.rabbitmq_url), timeout=30
            )
        except Exception as exc:
            logger.error("Could not connect to RabbitMQ: %s", exc)
            sys.exit(1)
        self.channel = await self.connection.channel()
        # Prefetch: each worker holds at most N unacknowledged messages, so
        # work spreads fairly across scaled-up worker instances.
        await self.channel.set_qos(prefetch_count=settings.prefetch_count)
        self.exchange, queues = await declare_topology(self.channel)
        queue = queues[self.queue_name]
        logger.info("%s listening on %s", self.worker_name, self.queue_name)
        async with queue.iterator() as it:
            async for message in it:
                try:
                    await self.on_message(message)
                except Exception:
                    logger.exception("on_message crashed; dead-lettering")
                    await message.nack(requeue=False)


def run_worker(worker: BaseWorker) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    )
    try:
        asyncio.run(worker.run())
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        # Exit non-zero so Docker's restart policy brings the worker back.
        logger.exception("Worker crashed: %s", exc)
        sys.exit(1)
