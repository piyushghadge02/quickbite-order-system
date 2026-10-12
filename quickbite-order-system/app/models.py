"""SQLAlchemy database models.

Three tables:
- orders:           every food order and its current status.
- notifications:    customer-facing messages produced by the notification worker.
- processed_events: idempotency records, one row per message already handled.
"""
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Order(Base):
    __tablename__ = "orders"

    order_id: Mapped[str] = mapped_column(String, primary_key=True)
    customer_name: Mapped[str] = mapped_column(String, nullable=False)
    restaurant_id: Mapped[str] = mapped_column(String, nullable=False)
    items_json: Mapped[str] = mapped_column(Text, nullable=False)  # JSON list of items
    total_amount: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="PENDING", index=True)
    driver_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # False until order.created has been confirmed by the broker.
    event_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    # The same event for the same order is stored at most once, even if the
    # message is delivered twice or two worker instances race.
    __table_args__ = (
        UniqueConstraint("order_id", "event_type", name="uq_notification_order_event"),
    )


class ProcessedEvent(Base):
    __tablename__ = "processed_events"

    # e.g. "order_abc123:order.created" — the primary key makes a second
    # insert of the same key fail, which is how duplicates are detected.
    idempotency_key: Mapped[str] = mapped_column(String, primary_key=True)
    worker: Mapped[str] = mapped_column(String, nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
