"""API tests: order creation, validation, retrieval, health."""
import pytest

from app.models import Order

ITEMS = [
    {"name": "Chicken Biryani", "quantity": 2, "price": 12.5},
    {"name": "Mango Lassi", "quantity": 1, "price": 4.0},
]

VALID_ORDER = {
    "customer_name": "Amina Khan",
    "restaurant_id": "rest_123",
    "items": ITEMS,
}


def test_create_order_valid(client, db_session_factory):
    resp = client.post("/orders", json=VALID_ORDER)
    assert resp.status_code == 201
    data = resp.json()
    assert data["order_id"].startswith("order_")
    assert data["status"] == "PENDING"
    assert data["total_amount"] == 29.0
    assert data["message"] == "Order accepted and queued for processing."

    # Persisted in SQLite with the published flag set.
    db = db_session_factory()
    try:
        order = db.get(Order, data["order_id"])
        assert order is not None
        assert order.status == "PENDING"
        assert order.total_amount == 29.0
        assert order.event_published is True
    finally:
        db.close()

    # Retrievable with full details.
    r2 = client.get(f"/orders/{data['order_id']}")
    assert r2.status_code == 200
    body = r2.json()
    assert body["customer_name"] == "Amina Khan"
    assert body["restaurant_id"] == "rest_123"
    assert body["items"] == ITEMS
    assert body["driver_id"] is None
    assert "created_at" in body and "updated_at" in body

    # order.created was published to the (fake) broker.
    assert len(client.rabbit.published) == 1
    routing_key, payload = client.rabbit.published[0]
    assert routing_key == "order.created"
    assert payload["order_id"] == data["order_id"]
    assert payload["idempotency_key"] == f"{data['order_id']}:order.created"


def test_total_amount_calculation(client):
    resp = client.post("/orders", json={
        "customer_name": "A", "restaurant_id": "r",
        "items": [{"name": "X", "quantity": 3, "price": 10.0},
                  {"name": "Y", "quantity": 2, "price": 2.5}],
    })
    assert resp.status_code == 201
    assert resp.json()["total_amount"] == 35.0  # 3*10.0 + 2*2.5


@pytest.mark.parametrize("body", [
    {"customer_name": "A", "restaurant_id": "r", "items": []},          # no items
    {"restaurant_id": "r", "items": ITEMS},                            # missing name
    {"customer_name": "", "restaurant_id": "r", "items": ITEMS},       # empty name
    {"customer_name": "A", "restaurant_id": "", "items": ITEMS},       # empty restaurant
    {"customer_name": "A", "restaurant_id": "r",
     "items": [{"name": "X", "quantity": 0, "price": 5}]},              # zero quantity
    {"customer_name": "A", "restaurant_id": "r",
     "items": [{"name": "X", "quantity": -1, "price": 5}]},            # negative quantity
    {"customer_name": "A", "restaurant_id": "r",
     "items": [{"name": "X", "quantity": 1, "price": -2.5}]},          # negative price
    {"customer_name": "A", "restaurant_id": "r",
     "items": [{"name": "X", "quantity": "two", "price": 5}]},         # wrong type
    {"customer_name": "A", "restaurant_id": "r",
     "items": [{"quantity": 1, "price": 5}]},                          # missing item name
])
def test_create_order_invalid(client, body):
    assert client.post("/orders", json=body).status_code == 422


def test_get_order_not_found(client):
    resp = client.get("/orders/order_nope123")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Order not found"


def test_health(client):
    data = client.get("/health").json()
    assert data["database_connected"] is True
    assert data["rabbitmq_connected"] is True  # the fake broker is "connected"
    assert data["status"] == "healthy"


def test_root_still_works(client):
    assert client.get("/").json() == {"message": "QuickBite API is running"}
