# RabbitMQ замість Kafka

У `compose.yaml` RabbitMQ немає, каркас працює лише з Kafka. Тут готова конфігурація з іменами
методички: `domain-events` (topic), `notifications` (fanout), черга обробника `worker`,
карантин `domain-events.dlq`. Шлюз оголошує власну чергу й прив'язує її до `notifications`,
тому кожен шлюз отримує всі сповіщення. Оголошуйте цю чергу ексклюзивною (exclusive) або
стійкою (durable): у RabbitMQ 4.3 тимчасові неексклюзивні черги типово заборонені.

Замініть у `compose.yaml` сервіси `broker`, `broker-init`, `kafka-ui` цим фрагментом, а
залежності від `broker-init` – на очікування готовності `broker`.

```yaml
  broker:
    image: rabbitmq:4.3.6-management
    volumes:
      - ./configs/broker/rabbitmq/rabbitmq.conf:/etc/rabbitmq/rabbitmq.conf:ro
      - ./configs/broker/rabbitmq/definitions.json:/etc/rabbitmq/definitions.json:ro
    ports:
      - "5672:5672"
      - "15672:15672"
    healthcheck:
      test:
        - "CMD"
        - "rabbitmq-diagnostics"
        - "-q"
        - "ping"
      interval: 5s
      retries: 30
```

```yaml
    depends_on:
      broker:
        condition: service_healthy
```

Процеси підключаються за адресою `amqp://app:app@broker:5672/`. Панель керування доступна
за адресою http://localhost:15672 (`app` / `app`).
