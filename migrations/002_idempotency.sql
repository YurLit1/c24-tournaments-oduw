CREATE TABLE idempotency_key (
  user_id      text        NOT NULL REFERENCES app_user (id),
  operation    text        NOT NULL CHECK (char_length(operation) BETWEEN 1 AND 64),
  key          text        NOT NULL CHECK (char_length(key) BETWEEN 8 AND 128),
  request_hash text        NOT NULL CHECK (char_length(request_hash) = 64),
  state        text        NOT NULL CHECK (state IN ('processing', 'done')),
  status_code  integer     CHECK (status_code BETWEEN 200 AND 599),
  location     text,
  response     json,
  created_at   timestamptz NOT NULL DEFAULT now(),
  expires_at   timestamptz NOT NULL,
  PRIMARY KEY (user_id, operation, key),
  CHECK (expires_at > created_at),
  CHECK ((state = 'done') = (status_code IS NOT NULL AND response IS NOT NULL))
);

CREATE INDEX idempotency_key_expires ON idempotency_key (expires_at);
