# Каркас сервера (приклад на Python 3.14, FastAPI)

Один образ запускає всі процеси, а який саме – задає `command` у `compose.yaml`. Каркас містить налаштування, службові маршрути й допоміжні модулі. Місця для пунктів позначено `TODO (Ox.y)`. Каркас можна доповнювати або замінити
реалізацією іншою мовою ([контракт середовища](../docs/ENVIRONMENT.md#інша-мова)).

| Модуль | Що дає |
|---|---|
| `main.py` | процес API (`app-a`, `app-b`, `app-canary`) і перелік місць для пунктів |
| `gateway.py` | процес шлюзу: `/v1/ws`, читання `notifications` у групі `GROUP_ID` |
| `publisher.py`, `worker.py`, `router.py` | заглушки фонових процесів |
| `config.py` | налаштування й режими дослідів зі змінних середовища |
| `db.py`, `cache.py`, `broker.py` | PostgreSQL, Redis, Kafka (`acks=all`, підтвердження після оброблення) |
| `middleware.py`, `jsonlog.py`, `metrics.py`, `telemetry.py` | `X-Request-ID`, журнал JSON, `/metrics`, траси OpenTelemetry |
| `problems.py` | помилки у форматі Problem Details |
| `service.py`, `lifecycle.py` | `/health`, `/ready` і прапорець завершення |
| `faults.py` | `fault("<місце>")` – керована відмова |

Запуск без контейнера виконується з цього каталогу. Інфраструктура з `compose.yaml` при цьому
має працювати.

```sh
uv sync
DATABASE_URL=postgresql://app:app@localhost:5432/app uv run uvicorn app.main:app --reload
```

На Windows цей спосіб не підключається до бази, бо асинхронний драйвер psycopg не працює зі
стандартним циклом подій Windows. Запускайте сервер у Docker (`docker compose up -d app-a`) або у WSL.
