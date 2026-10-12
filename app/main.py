
"""QuickBite Order Service: FastAPI API for creating and tracking food orders.

POST /orders saves the order in SQLite (status PENDING) and publishes an
order.created event to RabbitMQ. The order is committed to the database
before publishing, so an accepted order is never silently lost.
"""
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import SessionLocal, get_db, init_db
from .events import ORDER_CREATED, make_event
from .models import Order
from .rabbitmq import RabbitMQClient
from .schemas import CreateOrderRequest, CreateOrderResponse, HealthOut, OrderOut

logger = logging.getLogger("quickbite.api")

rabbitmq_client: RabbitMQClient | None = None


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def order_to_dict(order: Order) -> dict:
    return {
        "order_id": order.order_id,
        "customer_name": order.customer_name,
        "restaurant_id": order.restaurant_id,
        "items": json.loads(order.items_json),
        "total_amount": order.total_amount,
        "status": order.status,
        "driver_id": order.driver_id,
        "created_at": order.created_at.isoformat().replace("+00:00", "Z"),
        "updated_at": order.updated_at.isoformat().replace("+00:00", "Z"),
    }


async def connect_rabbitmq() -> None:
    """Connect to RabbitMQ with retries; keep the API available if unavailable."""
    global rabbitmq_client

    for attempt in range(1, 6):
        client = RabbitMQClient()
        try:
            await client.connect(timeout=15)
            rabbitmq_client = client
            logger.info("Connected to RabbitMQ successfully.")
            return
        except Exception as exc:
            logger.warning(
                "RabbitMQ connection attempt %s/5 failed: %s",
                attempt,
                exc,
            )
            try:
                await client.close()
            except Exception:
                pass

            if attempt < 5:
                await asyncio.sleep(5)

    logger.error(
        "RabbitMQ unavailable after 5 attempts. API will remain available."
    )


async def close_rabbitmq() -> None:
    global rabbitmq_client
    if rabbitmq_client is not None:
        await rabbitmq_client.close()
        rabbitmq_client = None


async def publish_order_created(order_dict: dict) -> bool:
    """Publish order.created with publisher confirms. Returns True on success."""
    if rabbitmq_client is None or not rabbitmq_client.is_connected:
        return False

    payload = make_event(
        ORDER_CREATED,
        order_dict["order_id"],
        customer_name=order_dict["customer_name"],
        restaurant_id=order_dict["restaurant_id"],
        items=order_dict["items"],
        total_amount=order_dict["total_amount"],
        created_at=order_dict["created_at"],
    )
    try:
        await rabbitmq_client.publish(ORDER_CREATED, payload)
        return True
    except Exception as exc:
        logger.warning("Failed to publish order.created: %s", exc)
        return False


async def republish_pending_events() -> None:
    """Re-publish order.created for orders saved but never published."""
    if rabbitmq_client is None:
        logger.warning("Skipping pending-event replay: RabbitMQ is unavailable.")
        return

    db = SessionLocal()
    try:
        pending = db.scalars(
            select(Order).where(Order.event_published == False)  # noqa: E712
        ).all()

        for order in pending:
            if await publish_order_created(order_to_dict(order)):
                order.event_published = True
                db.commit()
                logger.info("Re-published order.created for %s", order.order_id)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    await connect_rabbitmq()
    await republish_pending_events()
    yield
    await close_rabbitmq()


app = FastAPI(title="QuickBite Order Processing System", lifespan=lifespan)


@app.get("/")
def root():
    return {"message": "QuickBite API is running"}


@app.get("/health", response_model=HealthOut)
def health(db: Session = Depends(get_db)):
    try:
        db.execute(select(1))
        db_ok = True
    except Exception:
        db_ok = False

    rabbit_ok = rabbitmq_client is not None and rabbitmq_client.is_connected

    return {
        "status": "healthy" if (db_ok and rabbit_ok) else "degraded",
        "database_connected": db_ok,
        "rabbitmq_connected": rabbit_ok,
    }


@app.post("/orders", response_model=CreateOrderResponse, status_code=201)
async def create_order(payload: CreateOrderRequest, db: Session = Depends(get_db)):
    order_id = f"order_{uuid4().hex[:8]}"
    total = round(sum(item.quantity * item.price for item in payload.items), 2)

    order = Order(
        order_id=order_id,
        customer_name=payload.customer_name,
        restaurant_id=payload.restaurant_id,
        items_json=json.dumps([item.model_dump() for item in payload.items]),
        total_amount=total,
        status="PENDING",
    )
    db.add(order)
    db.commit()

    if await publish_order_created(order_to_dict(order)):
        order.event_published = True
        db.commit()
    else:
        logger.warning(
            "Order %s saved but order.created was NOT published",
            order_id,
        )

    return {
        "order_id": order_id,
        "status": "PENDING",
        "total_amount": total,
        "message": "Order accepted and queued for processing.",
    }


@app.get("/orders/{order_id}", response_model=OrderOut)
def get_order(order_id: str, db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order_to_dict(order)
