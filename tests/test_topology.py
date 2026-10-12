"""Topology test: declaring the RabbitMQ topology calls the right operations
with the right arguments (no broker needed; the channel is faked)."""

from app import rabbitmq as rabbitmq_module
from app.config import settings
from app.events import QUEUES


class FakeExchangeObj:
    def __init__(self, name):
        self.name = name


class FakeQueueObj:
    def __init__(self, channel, name):
        self._channel = channel
        self._name = name

    async def bind(self, exchange, routing_key=None):
        self._channel.bindings.append((self._name, exchange.name, routing_key))


class FakeChannel:
    def __init__(self):
        self.exchanges = {}
        self.queues = {}
        self.bindings = []

    async def declare_exchange(self, name, type, durable=False):
        self.exchanges[name] = {"type": type, "durable": durable}
        return FakeExchangeObj(name)

    async def declare_queue(self, name, durable=False, arguments=None):
        self.queues[name] = {"durable": durable, "arguments": arguments or {}}
        return FakeQueueObj(self, name)


def test_declare_topology():
    import asyncio

    async def _run():
        channel = FakeChannel()
        exchange, queues = await rabbitmq_module.declare_topology(channel)

        # Topic exchange, durable.
        assert exchange.name == settings.exchange_name
        assert channel.exchanges[settings.exchange_name]["durable"] is True

        # Dead-letter exchange + queue wired together.
        assert settings.dead_letter_queue in channel.queues
        assert channel.queues[settings.dead_letter_queue]["durable"] is True
        assert (settings.dead_letter_queue, settings.dead_letter_exchange, None) in channel.bindings

        # Every worker queue: durable, dead-lettered, bound to its routing keys.
        for queue_name, routing_keys in QUEUES.items():
            assert queue_name in channel.queues, queue_name
            q = channel.queues[queue_name]
            assert q["durable"] is True
            assert q["arguments"].get("x-dead-letter-exchange") == settings.dead_letter_exchange
            for rk in routing_keys:
                assert (queue_name, settings.exchange_name, rk) in channel.bindings, (queue_name, rk)

        # The notification queue really does get every order event.
        notif_bindings = [b for b in channel.bindings if b[0] == "notification.queue"]
        assert ("notification.queue", settings.exchange_name, "order.*") in notif_bindings

        assert set(queues) == set(QUEUES)

    asyncio.run(_run())
