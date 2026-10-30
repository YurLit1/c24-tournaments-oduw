set -u
BASE=${BASE:-http://localhost:8080}
P1='X-User-Id: u-player1'
P2='X-User-Id: u-player2'
P3='X-User-Id: u-player3'
JSON='Content-Type: application/json'
fail=0

docker compose exec -T postgres psql -q -U app -d app -c \
  "DELETE FROM registration WHERE tournament_id = 't-cs2'; UPDATE tournament SET available = slots WHERE id = 't-cs2';" \
  || { echo "не вдалося скинути дані: система запущена?"; exit 1; }

expect() {
  local name=$1 code=$2 ctype=$3; shift 3
  local out; out=$(curl -s -i "$@" | tr -d '\r')
  local got; got=$(printf '%s\n' "$out" | head -1 | awk '{print $2}')
  local ok=1
  [ "$got" = "$code" ] || ok=0
  [ "$ctype" = "-" ] || printf '%s\n' "$out" | grep -qi "^content-type: $ctype" || ok=0
  printf '%s\n' "$out" | grep -qi '^x-request-id:' || ok=0
  if [ $ok = 1 ]; then echo "OK   $name ($got)"; else echo "FAIL $name: очікували $code $ctype, отримали $got"; fail=1; fi
  LAST="$out"
}

expect "GET /health"                        200 application/json         "$BASE/health"
expect "GET /v1/tournaments"                200 application/json         "$BASE/v1/tournaments"
expect "POST: реєстрація"                   201 application/json         -X POST "$BASE/v1/registrations" -H "$P1" -H "$JSON" -d '{"tournament_id":"t-cs2","nickname":"neo"}'
printf '%s\n' "$LAST" | grep -qi '^location: /v1/registrations/' && echo "OK   Location є" || { echo "FAIL немає Location"; fail=1; }
LOC=$(printf '%s\n' "$LAST" | grep -i '^location:' | awk '{print $2}')
expect "GET власну реєстрацію"              200 application/json         "$BASE$LOC" -H "$P1"
expect "GET чужу реєстрацію"                404 application/problem+json "$BASE$LOC" -H "$P2"
expect "POST: повторна реєстрація"          409 application/problem+json -X POST "$BASE/v1/registrations" -H "$P1" -H "$JSON" -d '{"tournament_id":"t-cs2","nickname":"neo2"}'
expect "POST: пошкоджений JSON"             400 application/problem+json -X POST "$BASE/v1/registrations" -H "$P1" -H "$JSON" -d '{bad json'
expect "POST: короткий нікнейм"             422 application/problem+json -X POST "$BASE/v1/registrations" -H "$P1" -H "$JSON" -d '{"tournament_id":"t-cs2","nickname":"x"}'
expect "POST: турніру немає"                404 application/problem+json -X POST "$BASE/v1/registrations" -H "$P1" -H "$JSON" -d '{"tournament_id":"t-none","nickname":"neo"}'
expect "POST: другий гравець"               201 application/json         -X POST "$BASE/v1/registrations" -H "$P2" -H "$JSON" -d '{"tournament_id":"t-cs2","nickname":"trinity"}'
expect "POST: третій гравець, місць немає"  409 application/problem+json -X POST "$BASE/v1/registrations" -H "$P3" -H "$JSON" -d '{"tournament_id":"t-cs2","nickname":"morpheus"}'

inst=$(for i in 1 2 3 4 5 6; do curl -s "$BASE/health"; echo; done | grep -o 'app-[ab]' | sort -u | tr '\n' ' ')
[ "$inst" = "app-a app-b " ] && echo "OK   nginx передає запити app-a і app-b" || { echo "FAIL балансування: $inst"; fail=1; }

[ $fail = 0 ] && echo "Усі перевірки ЛР1 пройдено" || { echo "Є помилки"; exit 1; }
