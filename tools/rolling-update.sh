#!/bin/sh
# Rolling update template for lab 6 (O6.4): rebuild, then replace instances ONE BY ONE; the next
# one is replaced only when the new one answers GET /ready. Run from the project root:
#
#   tools/rolling-update.sh                          # app-a, then app-b
#   tools/rolling-update.sh app-a app-b worker gateway-a gateway-b
#   APP_TAG=v2 tools/rolling-update.sh               # roll out the image tagged v2
#
# Meanwhile run the load in another terminal and count failed requests (the guide: <= 0.5 %).
# Readiness is asked from inside the Compose network by a throw-away curl container, so the
# image of your server needs no tools and the instances need no published ports. Services
# without /ready (your publisher, worker) are replaced without waiting. What happens inside
# a process on SIGTERM (stop accepting, finish started requests) is item O6.3 of your code.
set -eu

COMPOSE="docker compose"
SERVICES="${*:-app-a app-b}"
PORT="${READY_PORT:-8000}"
CURL_IMAGE="curlimages/curl:8.10.1"

network() {
  docker inspect -f '{{range $name, $v := .NetworkSettings.Networks}}{{$name}} {{end}}' \
    "$($COMPOSE ps -q "$1")" | cut -d' ' -f1
}

wait_ready() {
  svc="$1"
  net="$(network "$svc")"
  i=0
  while [ "$i" -lt 60 ]; do
    if docker run --rm --network "$net" "$CURL_IMAGE" -fsS -m 2 "http://$svc:$PORT/ready" >/dev/null 2>&1; then
      echo "  $svc is ready"
      return 0
    fi
    i=$((i + 1))
    sleep 1
  done
  echo "  $svc is NOT ready after 60 s - stopping here; the other instances still serve" >&2
  exit 1
}

echo "building: $SERVICES"
$COMPOSE build $SERVICES
for svc in $SERVICES; do
  echo "replacing $svc"
  $COMPOSE up -d --no-deps --force-recreate "$svc"
  case "$svc" in
    app-*|gateway-*)
      wait_ready "$svc"
      $COMPOSE exec -T nginx nginx -t
      $COMPOSE exec -T nginx nginx -s reload
      sleep 3
      ;;
  esac
done
echo "done: $SERVICES replaced"
