"""Central configuration, read from environment variables with safe defaults.

Every service (API and all workers) reads the same settings, so the whole
system is configured in one place. Copy `.env.example` to `.env` to override.
"""
import os


class Settings:
    # SQLite database. In Docker this points at the shared volume (/data),
    # so the API and every worker use the same database file.
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./quickbite.db")

    # RabbitMQ connection URL.
    rabbitmq_url: str = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")

    # Topology names (must match the assignment).
    exchange_name: str = os.getenv("EXCHANGE_NAME", "quickbite.orders")
    dead_letter_exchange: str = os.getenv("DEAD_LETTER_EXCHANGE", "quickbite.dlx")
    dead_letter_queue: str = os.getenv("DEAD_LETTER_QUEUE", "orders.dead-letter.queue")

    # Reliability tuning.
    prefetch_count: int = int(os.getenv("PREFETCH_COUNT", "10"))
    max_retries: int = int(os.getenv("MAX_RETRIES", "3"))

    # Payment simulation: "off" | "random" | "transient" | "permanent".
    # "off" (default) always succeeds, so the happy path is clean.
    payment_fail_mode: str = os.getenv("PAYMENT_FAIL_MODE", "off")

    api_host: str = os.getenv("API_HOST", "127.0.0.1")
    api_port: int = int(os.getenv("API_PORT", "8000"))


settings = Settings()
