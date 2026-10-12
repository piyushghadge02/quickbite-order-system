"""Async RabbitMQ helper built on aio-pika.

One client per service. It declares the whole topology (exchange, queues,
bindings, dead-letter exchange) on connect — declaring is idempotent, so the
API and every worker can safely do it.
"""
import asyncio
import json
import logging

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message

from .config import settings
from .events import QUEUES

logger = logging.getLogger("quickbite.rabbitmq")


async def declare_topology(channel):
    """Declare exchange, dead-letter exchange, queues and bindings.

    Returns (exchange, queues_by_name). Safe to call from every service:
    RabbitMQ ignores re-declaration when the arguments match.
    """
    exchange = await channel.declare_exchange(
        settings.exchange_name, ExchangeType.TOPIC, durable=True
    )

    # Dead-letter exchange: a fanout exchange that collects messages from any
    # queue whose consumer nacks with requeue=False.
    dlx = await channel.declare_exchange(
        settings.dead_letter_exchange, ExchangeType.FANOUT, durable=True
    )
    dlq = await channel.declare_queue(settings.dead_letter_queue, durable=True)
    await dlq.bind(dlx)

    queues = {}
    for queue_name, routing_keys in QUEUES.items():
        queue = await channel.declare_queue(
            queue_name,
            durable=True,
            # Rejected (nack, requeue=False) messages go to the DLX instead
            # of being dropped.
            arguments={"x-dead-letter-exchange": settings.dead_letter_exchange},
        )
        for routing_key in routing_keys:
            await queue.bind(exchange, routing_key=routing_key)
        queues[queue_name] = queue
    return exchange, queues


class RabbitMQClient:
    """Thin wrapper around a robust aio-pika connection."""

    def __init__(self, url: str | None = None):
        self.url = url or settings.rabbitmq_url
        self.connection = None
        self.channel = None
        self.exchange = None

    @property
    def is_connected(self) -> bool:
        return self.connection is not None and not self.connection.is_closed

    async def connect(self, timeout: float = 15) -> None:
        # connect_robust auto-reconnects if the broker drops later.
        # wait_for bounds the *initial* wait so a down broker can't hang startup.
        self.connection = await asyncio.wait_for(
            aio_pika.connect_robust(self.url), timeout=timeout
        )
        # publisher_confirms=True: publish() waits for the broker's
        # confirmation and raises if the message was not accepted.
        self.channel = await self.connection.channel(publisher_confirms=True)
        self.exchange, _ = await declare_topology(self.channel)
        logger.info("Connected to RabbitMQ and declared topology")

    async def publish(self, routing_key: str, payload: dict, headers: dict | None = None) -> None:
        """Publish a persistent (survives broker restart) JSON message."""
        if not self.is_connected or self.exchange is None:
            raise RuntimeError("RabbitMQ is not connected")
        message = Message(
            body=json.dumps(payload).encode("utf-8"),
            delivery_mode=DeliveryMode.PERSISTENT,
            headers=headers or {},
            content_type="application/json",
        )
        await self.exchange.publish(message, routing_key=routing_key)

    async def close(self) -> None:
        if self.connection is not None:
            await self.connection.close()
            self.connection = None
