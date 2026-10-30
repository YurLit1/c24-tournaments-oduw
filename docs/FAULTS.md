# Керовані відмови

Особливо небезпечна відмова стається між двома діями, які неможливо виконати атомарно. Зміну вже зафіксовано, а відповідь чи підтвердження ще не
надіслано. Щоб довести, що система витримує відмову саме там, процес завершується в
названому місці коду на вимогу, а не випадково.

## Механізм

1. У потрібному місці коду стоїть перевірка, чи існує порожній файл `/faults/<ім'я>`.
   Файл не читається, перевіряється лише його наявність.
2. Якщо файл є, процес **видаляє його**, пише в журнал рядок `fault.hit` з іменем місця
   й **одразу завершується** з ненульовим кодом: без `finally`, без коректного завершення,
   без закриття з'єднань. Інакше вийде акуратна зупинка, а не аварія, і дослід нічого не доведе.
   Перевірка й видалення – це одна дія. Процес намагається видалити файл, і відмова спрацьовує лише тоді, коли видалення вдалося. Якщо спершу перевірити наявність, а потім видалити, два
   процеси (два екземпляри, два обробники) можуть одночасно пройти перевірку й завершитися
   обидва. Видалення файлу атомарне, тому з кількох процесів його виконає лише один.
3. Docker перезапускає процес (`restart: unless-stopped` у `compose.yaml`). Файлу вже
   немає, тож після перезапуску система працює звичайно, а відмова спрацювала один раз.
4. Перевірка працює лише за значення змінної `FAULTS=on`. У `compose.yaml` стенда вона ввімкнена.
   Якщо `FAULTS` не має значення `on`, перевірка не спрацьовує.

У Compose каталог `/faults` підключено до процесів через спільний том. У Web файл можна створити через `app-a`. Завдяки спільному тому його бачать і `app-b`, публікатор та обробник.

```sh
docker compose exec app-a touch /faults/after_commit_before_response
docker compose logs app-a app-b publisher worker
docker compose exec app-a rm -f /faults/after_commit_before_response
```

Між першою та другою командами виконується операція, що доходить до місця перевірки.
Запис `fault.hit` має з’явитися в журналі процесу, де розміщено цю
перевірку. Сам каркас її в предметний маршрут не вставляє. Остання команда вимикає
ще не спрацьовану відмову. Після аварії потрібні перевірка відновлення процесу,
повтор операції та перевірка, що ефект не подвоївся.

У Swarm томи типово локальні для вузла. Умови спільного каталогу й
налаштування `FAULTS` додатково описано в README конфігурації Swarm.

Параметр запиту чи змінна середовища для цього не підходять. Параметр дав би будь-якому клієнту змогу
зупинити сервер, а фонові процеси (публікатор, обробник) запитів не отримують. Змінна
задається під час запуску контейнера, і після перезапуску процес падав би знову й знову.

## Імена місць

Імена однакові для всіх тем. За ними відмову вмикають під час перевірки стенда.
Де саме в коді поставити перевірку – частина роботи.

| Курс | ЛР | Ім'я | Де стоїть перевірка |
|---|---|---|---|
| Web | 2 | `after_commit_before_response` | головну операцію зафіксовано, відповідь клієнту ще не надіслано |
| Web | 4 | `publisher_before_send` | публікатор узяв подію з таблиці вихідних подій, але ще не надіслав у брокер |
| Web | 4 | `after_external_before_commit` | обробник отримав відповідь симулятора, але ще не зафіксував результат |

Інші відмови з методичок робить Docker, файл для них не потрібен:
* зупинка шлюзу (`docker compose stop gateway-b`)
* сигнал завершення (`docker compose stop app-a`)

## Приклади

### Python

Є в каркасах (`app/faults.py`).

```python
def fault(place: str) -> None:
    if os.environ.get("FAULTS") != "on":
        return
    
    try:
        (Path("/faults") / place).unlink()
    except FileNotFoundError:
        return  # not armed, or another process took it first
    
    log("fault.hit", place=place)
    os._exit(1)
```

### Node.js

```javascript
function fault(place) {
  if (process.env.FAULTS !== "on") {
      return;
  }
  
  try {
    fs.unlinkSync(`/faults/${place}`);
  } catch {
    return; // not armed, or another process took it first
  }
  
  log("fault.hit", { place });
  process.exit(1);
}
```

### Go

```go
func fault(place string) {
	if os.Getenv("FAULTS") != "on" {
		return
	}

	faultPath := filepath.Join("/faults", place)
	
	if err := os.Remove(faultPath); err != nil {
		return
	}

	logHit(place)
	os.Exit(1)
}
```

### Java

```java
static void fault(String place) {
    if (!"on".equals(System.getenv("FAULTS"))) {
        return;
    }
    
    try {
        if (!Files.deleteIfExists(Path.of("/faults", place))) {
            return; // true only for the process that removed it
        }
    } catch (IOException e) {
        return;
    }
    
    logHit(place);
    Runtime.getRuntime().halt(1);
}
```

### C#

```csharp
static void Fault(string place)
{
    if (Environment.GetEnvironmentVariable("FAULTS") != "on")
    {
        return;
    }

    var flag = Path.Combine("/faults", place);
    var taken = $"{flag}.{Environment.ProcessId}";

    try
    {
        File.Move(flag, taken);
    }
    catch (FileNotFoundException)
    {
        return;
    }

    File.Delete(taken);
    LogHit(place);
    Environment.Exit(1);
}
```

Якщо сервер працює кількома робочими процесами, вихід завершує лише
один із них. Перевірте на своєму стеку, що клієнт справді не отримує відповіді, і опишіть
це в README.
