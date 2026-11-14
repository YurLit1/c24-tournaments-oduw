set -u
A=${APP_A:-http://localhost:8001}
B=${APP_B:-http://localhost:8002}
JSON='Content-Type: application/json'
fail=0

sql() { docker compose exec -T postgres psql -q -At -U app -d app -c "$1"; }
newkey() { echo "check-$(date +%s)-$RANDOM$RANDOM"; }
body() { printf '%s\n' "$LAST" | tail -1; }
header() { printf '%s\n' "$LAST" | grep -i "^$1:" | cut -d' ' -f2-; }
check() { if [ "$2" = "$3" ]; then echo "OK   $1"; else echo "FAIL $1: очікували '$3', отримали '$2'"; fail=1; fi; }

sql "DELETE FROM registration WHERE tournament_id = 't-cs2'; UPDATE tournament SET available = slots WHERE id = 't-cs2';" \
  || { echo "не вдалося скинути дані: система запущена?"; exit 1; }

P1='X-User-Id: u-player1'
P2='X-User-Id: u-player2'

expect() {
  local name=$1 code=$2; shift 2
  LAST=$(curl -s -i "$@" | tr -d '\r')
  local got; got=$(printf '%s\n' "$LAST" | head -1 | awk '{print $2}')
  if [ "$got" = "$code" ]; then echo "OK   $name ($got)"; else echo "FAIL $name: очікували $code, отримали $got"; fail=1; fi
}

K1=$(newkey)
expect "без Idempotency-Key"                    400 -X POST "$A/v1/registrations" -H "$P1" -H "$JSON" -d '{"tournament_id":"t-cs2","nickname":"neo"}'
expect "ключ коротший за 8 символів"            400 -X POST "$A/v1/registrations" -H "$P1" -H "Idempotency-Key: abc" -H "$JSON" -d '{"tournament_id":"t-cs2","nickname":"neo"}'
expect "перший запит через app-a"               201 -X POST "$A/v1/registrations" -H "$P1" -H "Idempotency-Key: $K1" -H "$JSON" -d '{"tournament_id":"t-cs2","nickname":"neo"}'
FIRST=$(body); LOC=$(header location)
expect "повтор через app-b, поля переставлено"  201 -X POST "$B/v1/registrations" -H "$P1" -H "Idempotency-Key: $K1" -H "$JSON" -d '{"nickname":"neo","tournament_id":"t-cs2"}'
check "та сама відповідь" "$(body)" "$FIRST"
check "той самий Location" "$(header location)" "$LOC"
check "відповів інший екземпляр" "$(header x-instance)" "app-b"
check "позначка повтору Idempotent-Replayed" "$(header idempotent-replayed)" "true"
expect "той самий ключ, інше тіло"              422 -X POST "$B/v1/registrations" -H "$P1" -H "Idempotency-Key: $K1" -H "$JSON" -d '{"tournament_id":"t-cs2","nickname":"neo2"}'

K2=$(newkey)
expect "новий ключ, гравець уже зареєстрований" 409 -X POST "$A/v1/registrations" -H "$P1" -H "Idempotency-Key: $K2" -H "$JSON" -d '{"tournament_id":"t-cs2","nickname":"neo3"}'
REFUSED=$(body)
expect "повтор відмови з тим самим ключем"      409 -X POST "$B/v1/registrations" -H "$P1" -H "Idempotency-Key: $K2" -H "$JSON" -d '{"tournament_id":"t-cs2","nickname":"neo3"}'
check "збережена відмова та сама" "$(body)" "$REFUSED"

K3=$(newkey)
sql "BEGIN; INSERT INTO idempotency_key (user_id, operation, key, request_hash, state, expires_at) VALUES ('u-player2', 'create-registration', '$K3', repeat('0', 64), 'processing', now() + interval '1 hour'); SELECT pg_sleep(3); ROLLBACK;" > /dev/null &
sleep 1
expect "ключ ще обробляється"                   409 -X POST "$A/v1/registrations" -H "$P2" -H "Idempotency-Key: $K3" -H "$JSON" -d '{"tournament_id":"t-cs2","nickname":"trinity"}'
printf '%s\n' "$LAST" | grep -q 'request-in-progress' && echo "OK   тип помилки request-in-progress" || { echo "FAIL тип помилки"; fail=1; }
check "Retry-After" "$(header retry-after)" "1"
wait

check "предметна зміна одна: реєстрацій гравця" "$(sql "SELECT count(*) FROM registration WHERE tournament_id = 't-cs2' AND user_id = 'u-player1'")" "1"
check "вільних місць t-cs2" "$(sql "SELECT available FROM tournament WHERE id = 't-cs2'")" "1"
check "ключ і результат збережено" "$(sql "SELECT state || ' ' || status_code FROM idempotency_key WHERE key = '$K1'")" "done 201"

sql "UPDATE idempotency_key SET created_at = now() - interval '2 days', expires_at = now() - interval '1 day' WHERE key IN ('$K1', '$K2');"
echo "     очікування прибирання прострочених ключів (до 40 с)"
left=2
for i in 1 2 3 4 5 6 7 8; do
  left=$(sql "SELECT count(*) FROM idempotency_key WHERE key IN ('$K1', '$K2')")
  [ "$left" = "0" ] && break
  sleep 5
done
check "прострочені ключі прибрано" "$left" "0"

[ $fail = 0 ] && echo "Усі перевірки ЛР2 пройдено" || { echo "Є помилки"; exit 1; }
