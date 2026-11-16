set -u
A=${APP_A:-http://localhost:8001}
B=${APP_B:-http://localhost:8002}
JSON='Content-Type: application/json'
fail=0

sql() { docker compose exec -T postgres psql -q -At -U app -d app -c "$1"; }
token() {
  curl -s -X POST "$A/v1/auth/login" -H "$JSON" -d "{\"login\":\"$1\",\"password\":\"$2\"}" \
    | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p'
}
body() { printf '%s\n' "$LAST" | tail -1; }
field() { body | sed -n "s/.*\"$1\":\"\{0,1\}\([^\",}]*\).*/\1/p"; }
check() { if [ "$2" = "$3" ]; then echo "OK   $1"; else echo "FAIL $1: очікували '$3', отримали '$2'"; fail=1; fi; }

sql "SELECT 1" > /dev/null \
  || { echo "не вдалося скинути дані: система запущена?"; exit 1; }

expect() {
  local name=$1 code=$2; shift 2
  LAST=$(curl -s -i "$@" | tr -d '\r')
  local got; got=$(printf '%s\n' "$LAST" | head -1 | awk '{print $2}')
  if [ "$got" = "$code" ]; then echo "OK   $name ($got)"; else echo "FAIL $name: очікували $code, отримали $got"; fail=1; fi
}

echo "--- О3.1 Вхід"
expect "вхід з неправильним паролем"            401 -X POST "$A/v1/auth/login" -H "$JSON" -d '{"login":"player1","password":"wrong"}'
expect "вхід через app-a"                       200 -X POST "$A/v1/auth/login" -H "$JSON" -d '{"login":"player1","password":"player-pass"}'
T1=$(field access_token); P1="Authorization: Bearer $T1"
[ -n "$(field expires_at)" ] && echo "OK   токен має строк дії expires_at" || { echo "FAIL немає expires_at"; fail=1; }
expect "GET /v1/me через app-b з тим самим токеном" 200 "$B/v1/me" -H "$P1"
check "роль гравця" "$(field role)" "user"
check "хеш токена в базі, а не сам токен" "$(sql "SELECT count(*) FROM session WHERE token_hash = '$T1'")" "0"
expect "заголовок X-User-Id більше не приймається" 401 "$B/v1/me" -H "X-User-Id: u-player1"
expect "запит без токена"                       401 "$A/v1/registrations/any"
P2="Authorization: Bearer $(token player2 player-pass)"
PS="Authorization: Bearer $(token organizer organizer-pass)"
expect "GET /v1/me організатора"                200 "$A/v1/me" -H "$PS"
check "роль організатора" "$(field role)" "staff"

echo "--- О3.1 Вихід і строк дії"
expect "вихід через app-b"                      204 -X POST "$B/v1/auth/logout" -H "$P1"
expect "старий токен після виходу, app-a"       401 "$A/v1/me" -H "$P1"
sql "UPDATE session SET created_at = now() - interval '9 hours', expires_at = now() - interval '1 hour' WHERE user_id = 'u-player2';"
expect "токен після завершення строку"          401 "$A/v1/me" -H "$P2"

[ $fail = 0 ] && echo "Усі перевірки ЛР3 пройдено" || { echo "Є помилки"; exit 1; }
