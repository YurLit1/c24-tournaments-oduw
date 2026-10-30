#!/bin/sh
# Starts nginx with the canary split (D6.2) from CANARY_WEIGHT, percent 0..100.
# nginx config cannot read environment variables and split_clients refuses 0 %.
set -eu

weight="${CANARY_WEIGHT:-0}"
mkdir -p /etc/nginx/generated
out=/etc/nginx/generated/canary.conf

case "$weight" in
  ''|*[!0-9]*) echo "CANARY_WEIGHT must be a whole number 0..100, got '$weight'" >&2; exit 1 ;;
esac

if [ "$weight" -eq 0 ]; then
  echo 'map $host $pool { default app; }' > "$out"
elif [ "$weight" -ge 100 ]; then
  echo 'map $host $pool { default canary; }' > "$out"
else
  cat > "$out" <<EOF
split_clients "\${http_authorization}\${remote_addr}" \$pool {
  ${weight}% canary;
  *          app;
}
EOF
fi
echo "canary weight: ${weight}%"
exec nginx -g 'daemon off;'
