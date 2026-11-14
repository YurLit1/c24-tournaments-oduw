import argparse
import json
import subprocess
import sys
import threading
import urllib.error
import urllib.request
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

sys.stdout.reconfigure(encoding="utf-8")

parser = argparse.ArgumentParser()
parser.add_argument("--tournament", default="t-race")
parser.add_argument("--players", type=int, default=200)
parser.add_argument("--instances", nargs="+", default=["http://localhost:8001", "http://localhost:8002"])
args = parser.parse_args()


def psql(sql: str) -> str:
    done = subprocess.run(
        ["docker", "compose", "exec", "-T", "postgres", "psql", "-U", "app", "-d", "app", "-At", "-c", sql],
        capture_output=True, text=True, encoding="utf-8")
    if done.returncode != 0:
        sys.exit(f"psql: {done.stderr.strip()}")
    return done.stdout.strip()


def post(url: str, body: dict, headers: dict) -> tuple[int, dict, str]:
    request = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(request, timeout=30) as reply:
            return reply.status, json.loads(reply.read()), reply.headers.get("X-Instance", "?")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}"), error.headers.get("X-Instance", "?")


psql(f"DELETE FROM registration WHERE tournament_id = '{args.tournament}'; "
     f"UPDATE tournament SET available = slots WHERE id = '{args.tournament}'")
slots = int(psql(f"SELECT slots FROM tournament WHERE id = '{args.tournament}'"))

numbers = range(1, args.players + 1)
start = threading.Barrier(args.players)


def register(n: int) -> tuple[int, str, str]:
    start.wait()
    status, body, instance = post(
        f"{args.instances[n % len(args.instances)]}/v1/registrations",
        {"tournament_id": args.tournament, "nickname": f"racer{n:03d}"},
        {"X-User-Id": f"u-race{n:03d}", "Idempotency-Key": str(uuid.uuid4())})
    return status, instance, body.get("type", "").rsplit("/", 1)[-1]


with ThreadPoolExecutor(args.players) as pool:
    results = list(pool.map(register, numbers))

statuses = Counter(status for status, _, _ in results)
created = Counter(instance for status, instance, _ in results if status == 201)
refused = Counter(kind for status, _, kind in results if status != 201)
available, active = psql(
    f"SELECT available, (SELECT count(*) FROM registration WHERE tournament_id = '{args.tournament}' "
    f"AND status IN ('held', 'confirmed')) FROM tournament WHERE id = '{args.tournament}'").split("|")

print(f"турнір {args.tournament}: місць {slots}, одночасних запитів {args.players}, "
      f"екземплярів {len(args.instances)}")
print("відповіді:", ", ".join(f"{code} - {count}" for code, count in sorted(statuses.items())))
print("201 за екземплярами:", ", ".join(f"{name} - {count}" for name, count in sorted(created.items())))
print("відмови:", ", ".join(f"{kind} - {count}" for kind, count in sorted(refused.items())) or "немає")
print(f"підсумок у базі: available = {available}, активних реєстрацій = {active}")

ok = (statuses[201] == min(slots, args.players) and int(active) == statuses[201]
      and int(available) == slots - statuses[201] and set(statuses) <= {201, 409})
print("ІНВАРІАНТ ЗБЕРЕЖЕНО" if ok else "ІНВАРІАНТ ПОРУШЕНО")
sys.exit(0 if ok else 1)
