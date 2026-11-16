CREATE TABLE session (
  token_hash text        PRIMARY KEY CHECK (char_length(token_hash) = 64),
  user_id    text        NOT NULL REFERENCES app_user (id),
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  CHECK (expires_at > created_at)
);

CREATE INDEX session_by_user ON session (user_id);
CREATE INDEX session_by_expires ON session (expires_at);
