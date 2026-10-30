#!/bin/sh
# Creates the topics "name:partitions" listed in TOPICS (the broker-init service runs it once).
# Existing topics are kept. To start an experiment from scratch see docs/ENVIRONMENT.md, "Kafka".
set -eu

BIN=/opt/kafka/bin
for t in $TOPICS; do
  "$BIN/kafka-topics.sh" --bootstrap-server "$BOOTSTRAP" --create --if-not-exists \
    --topic "${t%%:*}" --partitions "${t##*:}" --replication-factor 1
done
"$BIN/kafka-topics.sh" --bootstrap-server "$BOOTSTRAP" --list
