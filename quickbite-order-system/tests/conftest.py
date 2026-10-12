"""Shared fixtures: isolated SQLite database and a FastAPI TestClient whose
RabbitMQ calls go to a fake (no broker needed for the API tests)."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.main as main_module
from app import models
from app.database import get_db


class FakeRabbitMQ:
    """Stands in for RabbitMQClient: records published events, no network."""

    def __init__(self):
        self.published = []  # list of (routing_key, payload)
        self._connected = True

    @property
    def is_connected(self):
        return self._connected

    async def publish(self, routing_key, payload, headers=None):
        self.published.append((routing_key, payload))

    async def close(self):
        self._connected = False


@pytest.fixture()
def db_session_factory(tmp_path):
    db_file = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_file}", connect_args={"check_same_thread": False}
    )
    models.Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def client(db_session_factory, monkeypatch):
    fake = FakeRabbitMQ()

    async def _fake_connect():
        main_module.rabbitmq_client = fake

    monkeypatch.setattr(main_module, "init_db", lambda: None)
    monkeypatch.setattr(main_module, "connect_rabbitmq", _fake_connect)
    monkeypatch.setattr(main_module, "SessionLocal", db_session_factory)

    def _override():
        db = db_session_factory()
        try:
            yield db
        finally:
            db.close()

    main_module.app.dependency_overrides[get_db] = _override
    with TestClient(main_module.app) as test_client:
        test_client.rabbit = fake  # handy handle for assertions
        yield test_client
    main_module.app.dependency_overrides.clear()
