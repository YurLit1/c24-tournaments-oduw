# Docker Swarm (Д6.4)

Потрібні два вузли. Команди – з кореня проєкту на першому вузлі.

```sh
docker swarm init --advertise-addr <IP>            # на другому вузлі – надрукована команда join
docker node update --label-add db=true <вузол>     # тут працюватимуть postgres і broker

docker service create --name registry --publish 5000:5000 registry:2
docker build -t localhost:5000/project-web:dev ./server
docker build -t localhost:5000/project-external-sim:dev ./tools/external-sim
docker build -f configs/swarm/Dockerfile.migrate -t localhost:5000/project-migrate:dev .
docker push localhost:5000/project-web:dev
docker push localhost:5000/project-external-sim:dev
docker push localhost:5000/project-migrate:dev

docker stack deploy -c configs/swarm/stack.yaml web
docker service ps web_app
docker build -t localhost:5000/project-web:v2 ./server
docker push localhost:5000/project-web:v2
docker service update --image localhost:5000/project-web:v2 web_app
```

`app` і `gateway` мають по два завдання (task), не більше одного на вузол.
Оновлення `stop-first` спочатку зупиняє одне старе завдання й запускає заміну на звільненому
вузлі. Тимчасово лишається один екземпляр. Третій вузол для заміни не потрібен.
Для `app` задано перевірку `/ready` і автоматичний відкат за помилки в межах `monitor`.
У `gateway` немає такої перевірки й автоматичного відкату. Його підключення та відновлення
клієнтів перевіряються окремо. Сам успіх команди оновлення не підтверджує готовності.

Симулятор зберігає результати в томі `simdata` на вузлі з міткою `db=true`.
Цю мітку має рівно один вузол. Перезапуск на ньому зберігає дані. Втрата вузла
або перенесення мітки на інший вузол не переносить локальний том.

## Керовані відмови

У базовому стеку `FAULTS=off`, бо локальні томи різних вузлів не утворюють спільного каталогу.
Конфігурація [faults.yaml](faults.yaml) вмикає механізм і підключає `/faults`. Для неї на кожному
вузлі в один абсолютний шлях, наприклад `/srv/course-faults`, змонтовано **ту саму спільну файлову
систему**. Вона підтримує атомарне видалення файлу між клієнтами й дозволяє запис контейнерам.
Окремі локальні каталоги з однаковими назвами не підходять.

```sh
export FAULTS_DIR=/srv/course-faults
docker stack deploy -c configs/swarm/stack.yaml -c configs/swarm/faults.yaml web
```

Файл точки відмови створюють у цьому каталозі, а журнал перевіряють через
`docker service logs <ім’я_сервісу>`. Механізм та імена точок описано в [FAULTS.md](../../docs/FAULTS.md).

## Реєстр і змінні

Стек бере образи з реєстру, доступного з усіх вузлів. Наведений локальний реєстр призначений
для навчального середовища, інший задається через `REGISTRY`. `docker stack deploy` не читає
`.env`, тому потрібні змінні експортуйте в оболонці.
