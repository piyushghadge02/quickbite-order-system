"""Pydantic schemas: HTTP request/response validation."""
from pydantic import BaseModel, Field


class OrderItem(BaseModel):
    name: str = Field(min_length=1)
    quantity: int = Field(gt=0)
    price: float = Field(gt=0)


class CreateOrderRequest(BaseModel):
    customer_name: str = Field(min_length=1)
    restaurant_id: str = Field(min_length=1)
    items: list[OrderItem] = Field(min_length=1)


class OrderItemOut(BaseModel):
    name: str
    quantity: int
    price: float


class OrderOut(BaseModel):
    order_id: str
    customer_name: str
    restaurant_id: str
    items: list[OrderItemOut]
    total_amount: float
    status: str
    driver_id: str | None = None
    created_at: str
    updated_at: str


class CreateOrderResponse(BaseModel):
    order_id: str
    status: str
    total_amount: float
    message: str


class HealthOut(BaseModel):
    status: str
    database_connected: bool
    rabbitmq_connected: bool
