"""RabbitMQ helpers for async agent communication."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from common.config import get_settings


class RabbitMQPublisher:
    """Lightweight synchronous RabbitMQ publisher."""

    def __init__(self) -> None:
        settings = get_settings()
        self._url = settings.rabbitmq_url
        try:
            import pika

            self._pika = pika
            self._parameters = pika.URLParameters(settings.rabbitmq_url)
        except ImportError:
            self._pika = None
            self._parameters = None

    def publish(self, queue_name: str, message: dict[str, Any]) -> None:
        """Publish a JSON message to a durable queue."""

        if self._pika is None or self._parameters is None:
            fallback_dir = Path(".local_queue")
            fallback_dir.mkdir(parents=True, exist_ok=True)
            queue_file = fallback_dir / f"{queue_name}.jsonl"
            with queue_file.open("a", encoding="utf-8") as file:
                file.write(json.dumps(message, ensure_ascii=False) + "\n")
            return

        connection = self._pika.BlockingConnection(self._parameters)
        channel = connection.channel()
        channel.queue_declare(queue=queue_name, durable=True)
        channel.basic_publish(
            exchange="",
            routing_key=queue_name,
            body=json.dumps(message, ensure_ascii=False).encode("utf-8"),
            properties=self._pika.BasicProperties(delivery_mode=2),
        )
        connection.close()
