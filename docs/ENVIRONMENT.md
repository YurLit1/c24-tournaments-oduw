# Середовище Docker Compose

Конфігурація – [compose.yaml](../compose.yaml). Запуск стенда й адреси сервісів описано в
[README](../README.md#запуск). Усі команди виконуються з кореня каталогу курсу. Приклади
команд наведено для Bash.

## Kafka

Тема (topic) Kafka об’єднує повідомлення одного потоку. Команди нижче стосуються навчальних даних. Видалення теми стирає її повідомлення.

```sh
docker compose exec broker /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server broker:9092 \
  --topic domain-events --from-beginning --property print.key=true --property print.headers=true
docker compose exec broker /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server broker:9092 --describe --all-groups
# почати дослід заново: зупинити читачів, видалити теми, створити знову
docker compose stop publisher worker gateway-a gateway-b router
docker compose exec broker /opt/kafka/bin/kafka-topics.sh --bootstrap-server broker:9092 --delete --topic 'domain-events.*|notifications'
docker compose run --rm broker-init && docker compose start publisher worker gateway-a gateway-b router
```

Групи споживачів задає `GROUP_ID`: `worker`, `gateway-a`, `gateway-b`, `router`.

## План запиту (Д2.7)

Для схеми з прикладу спершу створюються користувачі `bulk000…bulk499`, потім 10⁵ закритих бронювань.

```sh
docker compose exec -T postgres psql -U app -c "INSERT INTO app_user (id, login, name, password_hash, role)
  SELECT 'bulk' || lpad(i::text, 3, '0'), 'bulk' || lpad(i::text, 3, '0'), 'Bulk', '-', 'user'
  FROM generate_series(0, 499) AS i"
python tools/generator/generate.py tools/generator/spec.example.json 100000 > rows.csv
docker compose exec -T postgres psql -U app \
  -c "\copy hold (id, user_id, branch_id, book_id, status, created_at, expires_at) FROM STDIN CSV" < rows.csv
docker compose exec -T postgres psql -U app -c "EXPLAIN (ANALYZE, BUFFERS)
  SELECT id FROM hold WHERE user_id = 'bulk007' ORDER BY created_at DESC, id DESC LIMIT 21"
```

`tools/generator/demo.example.json` – невеликий набір бронювань у різних станах для показу клієнта.

## Попередня версія (О6.2, О6.4)

```sh
git worktree add ../v1 <коміт попередньої версії>
docker build -t project-web:v1 ../v1/server
APP_TAG=v1 docker compose up -d --no-build app-a app-b      # стара версія
APP_TAG=dev tools/rolling-update.sh                          # оновлення екземплярів по одному
```

## Поступове оновлення

`tools/rolling-update.sh` і `tools/rolling-update.ps1` замінюють екземпляри по одному.
Після відповіді `/ready` скрипт перевіряє конфігурацію nginx та надсилає сигнал її перечитування,
щоб повторно визначити адреси сервісів. Помилка команди зупиняє оновлення.
PowerShell-варіант визначає опублікований порт через `docker compose port`.
Перечитування nginx не доводить відсутності втрачених запитів. Це перевіряється навантаженням.
Сценарій гонки з двох запитів для тривалого навантаження не підходить.
Після ручного повторного створення контейнерів сервісів також потрібні `docker compose exec -T nginx nginx -t`
і `docker compose exec -T nginx nginx -s reload`.

[Керування nginx](https://nginx.org/en/docs/control.html) описує перечитування конфігурації
та завершення старих робочих процесів після обслуговування їхніх клієнтів.

## Інша мова

Замініть `server/Dockerfile` і рядки `command` у `compose.yaml`. Решта інфраструктури
від мови не залежить, якщо процес:

- слухає порт `8000` у контейнері й читає налаштування зі змінних середовища (`compose.yaml`);
- має `/health`, `/ready` (і `/metrics` для Prometheus, якщо потрібні панелі Grafana);
- пише журнал JSON у stdout з полями `time`, `instance`, `route`, `status`, `duration_ms`
  (інші назви – у `log_fields` файлу `checks.yaml`);
- реалізує керовані відмови за [FAULTS.md](FAULTS.md) і коректно завершується за SIGTERM;
- надсилає траси OTLP HTTP на `OTEL_EXPORTER_OTLP_ENDPOINT` засобами своєї мови.

## Типові проблеми

| Симптом | Що зробити |
|---|---|
| `port is already allocated` | змінити порт у `.env` |
| `\r: not found` у скрипті | файл `.sh` має кінці рядків CRLF. Виконати `git config core.autocrlf input` і клонувати заново |
| `publisher`, `worker`, шлюзи не стартують | Kafka ще запускається. Переглянути `docker compose logs broker broker-init`, потім виконати `docker compose up -d` |
| `migrate` завершився з помилкою | переглянути `docker compose logs migrate` і виправити останній доданий файл міграції |
| контейнери зупиняються через брак пам'яті | збільшити пам'ять Docker або зупинити непотрібні сервіси (`docker compose stop keycloak jaeger grafana`) |

## Довідник компонентів

| Компонент або можливість | Налаштування чи команда |
|---|---|
| приклад контракту | `npx @redocly/cli lint openapi.yaml` |
| nginx `least_conn`, `X-Request-ID`, журнал JSON | `docker compose logs -f app-a app-b nginx` |
| траси OpenTelemetry → Jaeger | `OTEL_ENABLED=on` у `.env`, `docker compose up -d` |
| гонка через обидва екземпляри | [tools/workload](../tools/workload/README.md) |
| керовані відмови | [FAULTS.md](FAULTS.md) |
| Redis | `server/app/cache.py` |
| `PG_MAX_CONNECTIONS`, `POOL_SIZE` | екземпляри × `POOL_SIZE` + фонові процеси < `PG_MAX_CONNECTIONS` |
| генератор 10⁵ рядків, `psql` | розділ «План запиту» |
| клієнт на :8081, сторонній сайт | `python -m http.server 8082 --directory tools/evil-origin` |
| Keycloak, realm `project`, клієнт `web-client` / `web-client-secret`, `user1` / `user1-pass`, `staff1` / `staff1-pass` | `configs/keycloak/realm-project.json` |
| Kafka, симулятор, заглушки `publisher`, `worker` | [tools/external-sim](../tools/external-sim/README.md) |
| конверт CloudEvents, канали | `asyncapi.example.yaml` |
| тема (topic) `domain-events.dlq` | Kafka UI |
| шлюзи, `/v1/ws` у nginx, `ws-fleet` | `node tools/ws-fleet.mjs --tokens tokens.txt --connections 20 --watch 60` |
| `/v1/sse` без буферизації; `proxy_read_timeout 1h` | `configs/nginx/nginx.conf` |
| повільний клієнт | `uv run tools/slow-ws-client.py <login> <password>` |
| `MIGRATE_TO` | [migrations/README.md](../migrations/README.md) |
| стара версія як образ; формат збережених запитів | розділ «Попередня версія»; [compat-table.md](compat-table.md) |
| `stop_grace_period: 30s`; nginx повторює GET на іншому екземплярі після 502/503 | `tools/rolling-update.sh` (або `.ps1`) |
| канаркове оновлення (`app-canary`, частка трафіку `CANARY_WEIGHT`) | `CANARY_TAG=v2 CANARY_WEIGHT=10 docker compose up -d --build app-canary nginx` |
| сервіс прапорців flagd, `configs/flags/flags.json` | `curl -X POST localhost:8099/ofrep/v1/evaluate/flags/new-behaviour -d '{"context":{}}'` |
| стек Swarm | [configs/swarm/README.md](../configs/swarm/README.md) |
