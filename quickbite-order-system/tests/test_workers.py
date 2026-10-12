"""Worker logic tests using fake broker objects (no RabbitMQ needed).

FakeMessage mimics the slice of aio-pika's IncomingMessage that BaseWorker
uses: .body, .headers, .routing_key, .ack(), .nack(requeue=...).
"""
import asyncio
import json

from app import models
from app.config import settings
from app.events import DRIVER_ASSIGNED, ORDER_CONFIRMED, ORDER_CREATED, ORDER_PAID
from workers.delivery_worker import DeliveryWorker
from workers.notification_worker import NotificationWorker
from workers.payment_worker import PaymentWorker
from workers.restaurant_worker import RestaurantWorker


class FakeMessage:
    def __init__(self, payload=None, routing_key="order.created",
                 headers=None, raw_body=None):
        self.body = raw_body if raw_body is not None else json.dumps(payload).encode()
        self.routing_key = routing_key
        self.headers = headers or {}
        self.acked = False
        self.nacked = None  # None = never nacked; otherwise the requeue flag

    async def ack(self):
        self.acked = True

    async def nack(self, requeue=True):
        self.nacked = requeue


class FakeExchange:
    def __init__(self):
        self.published = []  # (routing_key, payload_dict, headers_dict)

    async def publish(self, message, routing_key, **kwargs):
        self.published.append(
            (routing_key, json.loads(message.body.decode()), dict(message.headers or {}))
        )


async def _no_sleep(*args, **kwargs):
    return None


def make_worker(worker_cls, db_session_factory):
    worker = worker_cls(session_factory=db_session_factory)
    worker.exchange = FakeExchange()
    return worker


def seed_order(db_session_factory, order_id="order_test123", status="PENDING"):
    db = db_session_factory()
    try:
        db.add(models.Order(
            order_id=order_id, customer_name="Amina Khan", restaurant_id="rest_123",
            items_json=json.dumps([{"name": "X", "quantity": 1, "price": 5.0}]),
            total_amount=5.0, status=status,
        ))
        db.commit()
    finally:
        db.close()
    return order_id


def order_created_payload(order_id):
    return {
        "event_type": ORDER_CREATED,
        "order_id": order_id,
        "idempotency_key": f"{order_id}:{ORDER_CREATED}",
    }


def get_order(db_session_factory, order_id):
    db = db_session_factory()
    try:
        return db.get(models.Order, order_id)
    finally:
        db.close()


# ---------------------------------------------------------------- payment ---

def test_payment_success(db_session_factory, monkeypatch):
    monkeypatch.setattr(settings, "payment_fail_mode", "off")
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)
    order_id = seed_order(db_session_factory)
    worker = make_worker(PaymentWorker, db_session_factory)

    asyncio.run(worker.on_message(FakeMessage(order_created_payload(order_id))))

    assert get_order(db_session_factory, order_id).status == "PAID"
    assert len(worker.exchange.published) == 1
    rk, payload, _ = worker.exchange.published[0]
    assert rk == ORDER_PAID
    assert payload["order_id"] == order_id
    assert payload["payment_id"].startswith("pay_")


def test_payment_transient_retry_then_dead_letter(db_session_factory, monkeypatch):
    monkeypatch.setattr(settings, "payment_fail_mode", "transient")
    monkeypatch.setattr(settings, "max_retries", 2)
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)
    order_id = seed_order(db_session_factory)
    worker = make_worker(PaymentWorker, db_session_factory)

    # Attempt 1: transient failure -> republished with retry count 1, original acked.
    msg1 = FakeMessage(order_created_payload(order_id))
    asyncio.run(worker.on_message(msg1))
    assert msg1.acked and msg1.nacked is None
    assert get_order(db_session_factory, order_id).status == "PENDING"
    rk, _, headers = worker.exchange.published[0]
    assert rk == ORDER_CREATED and headers["x-retry-count"] == 1

    # Attempt 2 (redelivery): retry count 2.
    msg2 = FakeMessage(order_created_payload(order_id), headers={"x-retry-count": 1})
    asyncio.run(worker.on_message(msg2))
    _, _, headers2 = worker.exchange.published[1]
    assert headers2["x-retry-count"] == 2

    # Attempt 3: retries exhausted -> PAYMENT_FAILED, order.payment.failed,
    # original nacked with requeue=False (broker dead-letters it).
    msg3 = FakeMessage(order_created_payload(order_id), headers={"x-retry-count": 2})
    asyncio.run(worker.on_message(msg3))
    assert msg3.nacked is False and not msg3.acked
    assert get_order(db_session_factory, order_id).status == "PAYMENT_FAILED"
    final = [p for p in worker.exchange.published if p[0] == "order.payment.failed"]
    assert len(final) == 1 and final[0][1]["order_id"] == order_id


def test_payment_permanent_failure_no_retry(db_session_factory, monkeypatch):
    monkeypatch.setattr(settings, "payment_fail_mode", "permanent")
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)
    order_id = seed_order(db_session_factory)
    worker = make_worker(PaymentWorker, db_session_factory)

    msg = FakeMessage(order_created_payload(order_id))
    asyncio.run(worker.on_message(msg))

    assert msg.nacked is False and not msg.acked  # straight to the DLQ
    assert get_order(db_session_factory, order_id).status == "PAYMENT_FAILED"
    routing_keys = [rk for rk, _, _ in worker.exchange.published]
    assert routing_keys == ["order.payment.failed"]  # no retry republish


def test_payment_duplicate_delivery_processed_once(db_session_factory, monkeypatch):
    monkeypatch.setattr(settings, "payment_fail_mode", "off")
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)
    order_id = seed_order(db_session_factory)
    worker = make_worker(PaymentWorker, db_session_factory)
    payload = order_created_payload(order_id)

    msg1 = FakeMessage(payload)
    asyncio.run(worker.on_message(msg1))
    msg2 = FakeMessage(payload)  # redelivered duplicate
    asyncio.run(worker.on_message(msg2))

    assert msg1.acked and msg2.acked
    assert len(worker.exchange.published) == 1  # order.paid emitted only once


def test_payment_missing_order_dead_lettered(db_session_factory, monkeypatch):
    monkeypatch.setattr(settings, "payment_fail_mode", "off")
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)
    worker = make_worker(PaymentWorker, db_session_factory)

    msg = FakeMessage(order_created_payload("order_ghost"))
    asyncio.run(worker.on_message(msg))

    assert msg.nacked is False  # permanent: nothing to charge, don't retry


def test_malformed_message_goes_to_dead_letter(db_session_factory):
    worker = make_worker(PaymentWorker, db_session_factory)
    msg = FakeMessage(raw_body=b"this is not json{{{")
    asyncio.run(worker.on_message(msg))
    assert msg.nacked is False and not msg.acked


# ------------------------------------------------- restaurant + delivery ---

def test_restaurant_and_delivery_flow(db_session_factory, monkeypatch):
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)
    order_id = seed_order(db_session_factory, status="PAID")
    restaurant = make_worker(RestaurantWorker, db_session_factory)
    delivery = make_worker(DeliveryWorker, db_session_factory)

    paid_payload = {"event_type": ORDER_PAID, "order_id": order_id,
                    "idempotency_key": f"{order_id}:{ORDER_PAID}"}
    rmsg = FakeMessage(paid_payload, routing_key=ORDER_PAID)
    asyncio.run(restaurant.on_message(rmsg))
    assert rmsg.acked
    assert get_order(db_session_factory, order_id).status == "CONFIRMED"
    assert restaurant.exchange.published[0][0] == ORDER_CONFIRMED

    confirmed_payload = restaurant.exchange.published[0][1]
    dmsg = FakeMessage(confirmed_payload, routing_key=ORDER_CONFIRMED)
    asyncio.run(delivery.on_message(dmsg))
    assert dmsg.acked
    order = get_order(db_session_factory, order_id)
    assert order.status == "DRIVER_ASSIGNED"
    assert order.driver_id.startswith("driver_")
    rk, payload, _ = delivery.exchange.published[0]
    assert rk == DRIVER_ASSIGNED and payload["driver_id"] == order.driver_id


# ------------------------------------------------------------ notification ---

def test_notification_dedup(db_session_factory):
    worker = make_worker(NotificationWorker, db_session_factory)
    payload = {"event_type": ORDER_PAID, "order_id": "order_n1",
               "idempotency_key": "order_n1:order.paid"}

    asyncio.run(worker.on_message(FakeMessage(payload, routing_key=ORDER_PAID)))
    asyncio.run(worker.on_message(FakeMessage(payload, routing_key=ORDER_PAID)))

    db = db_session_factory()
    try:
        rows = db.query(models.Notification).all()
        assert len(rows) == 1
        assert "Payment successful" in rows[0].message
    finally:
        db.close()


def test_notification_texts(db_session_factory):
    worker = make_worker(NotificationWorker, db_session_factory)
    payload = {"event_type": ORDER_CREATED, "order_id": "order_n2",
               "idempotency_key": "order_n2:order.created"}
    asyncio.run(worker.on_message(FakeMessage(payload, routing_key=ORDER_CREATED)))
    db = db_session_factory()
    try:
        row = db.query(models.Notification).one()
        assert row.message == "Your order order_n2 has been received."
    finally:
        db.close()


# ---------------------------------------------------------------- full chain ---

def test_full_chain_end_to_end(db_session_factory, monkeypatch):
    """order.created -> paid -> confirmed -> driver_assigned, plus notifications."""
    monkeypatch.setattr(settings, "payment_fail_mode", "off")
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)
    order_id = seed_order(db_session_factory)

    payment = make_worker(PaymentWorker, db_session_factory)
    restaurant = make_worker(RestaurantWorker, db_session_factory)
    delivery = make_worker(DeliveryWorker, db_session_factory)
    notify = make_worker(NotificationWorker, db_session_factory)

    asyncio.run(payment.on_message(FakeMessage(order_created_payload(order_id))))
    paid = payment.exchange.published[0][1]
    asyncio.run(restaurant.on_message(FakeMessage(paid, routing_key=ORDER_PAID)))
    confirmed = restaurant.exchange.published[0][1]
    asyncio.run(delivery.on_message(FakeMessage(confirmed, routing_key=ORDER_CONFIRMED)))
    assigned = delivery.exchange.published[0][1]

    # The notification queue's "order.*" binding delivers every event.
    for routing_key, event_payload in [
        (ORDER_CREATED, order_created_payload(order_id)),
        (ORDER_PAID, paid),
        (ORDER_CONFIRMED, confirmed),
        (DRIVER_ASSIGNED, assigned),
    ]:
        asyncio.run(notify.on_message(FakeMessage(event_payload, routing_key=routing_key)))

    order = get_order(db_session_factory, order_id)
    assert order.status == "DRIVER_ASSIGNED"
    assert order.driver_id.startswith("driver_")

    db = db_session_factory()
    try:
        assert db.query(models.Notification).count() == 4
        # 3 pipeline workers + 4 notification events = 7 idempotency records,
        # namespaced per worker so nothing clashes.
        assert db.query(models.ProcessedEvent).count() == 7
    finally:
        db.close()
