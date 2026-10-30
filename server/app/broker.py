"""Thin helpers over Kafka (aiokafka) for the publisher, the handler and the gateways.

They only connect, send and read. What is sent, when a message counts as processed, which
consumer group a process uses (one per handler, one per gateway or one shared) are the
decisions of labs 4 and 5. With RabbitMQ instead of Kafka write the same two helpers for it.
"""

import json
from collections.abc import Awaitable, Callable

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.structs import ConsumerRecord

from . import config


async def start_producer() -> AIOKafkaProducer:
    """acks="all": send() returns after the broker stored the message (O4.2 relies on this)."""
    producer = AIOKafkaProducer(bootstrap_servers=config.KAFKA_BOOTSTRAP, acks="all", enable_idempotence=True)
    await producer.start()
    return producer


async def send(
    producer: AIOKafkaProducer, topic: str, key: str, value: dict, headers: dict[str, str] | None = None
) -> None:
    await producer.send_and_wait(
        topic,
        key=key.encode(),
        value=json.dumps(value, ensure_ascii=False).encode(),
        headers=[(name, data.encode()) for name, data in (headers or {}).items()],
    )


async def consume(topic: str, group_id: str, handle: Callable[[ConsumerRecord], Awaitable[None]]) -> None:
    """Read `topic` in `group_id`; the offset is committed only after `handle` returned.

    If `handle` raises, the offset is not committed and the process stops: after a restart the
    message comes again. Retries with a pause and the quarantine (D4.4) are yours to add.
    """
    consumer = AIOKafkaConsumer(
        topic,
        bootstrap_servers=config.KAFKA_BOOTSTRAP,
        group_id=group_id,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    await consumer.start()
    try:
        async for record in consumer:
            await handle(record)
            await consumer.commit()
    finally:
        await consumer.stop()
