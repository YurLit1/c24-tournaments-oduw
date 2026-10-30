CREATE TABLE app_user (
  id            text PRIMARY KEY,
  login         text NOT NULL UNIQUE,
  name          text NOT NULL,
  password_hash text NOT NULL,
  role          text NOT NULL CHECK (role IN ('user', 'staff'))
);

CREATE TABLE tournament (
  id                text        PRIMARY KEY,
  game              text        NOT NULL CHECK (char_length(game) BETWEEN 1 AND 100),
  starts_at         timestamptz NOT NULL,
  time_zone         text        NOT NULL DEFAULT 'Europe/Kyiv',
  slots             integer     NOT NULL CHECK (slots > 0),
  available         integer     NOT NULL,
  fee_minor         bigint      NOT NULL CHECK (fee_minor >= 0),
  currency          char(3)     NOT NULL DEFAULT 'UAH' CHECK (currency ~ '^[A-Z]{3}$'),
  registration_open boolean     NOT NULL DEFAULT true,
  created_at        timestamptz NOT NULL DEFAULT now(),
  CHECK (available BETWEEN 0 AND slots)
);

CREATE TABLE registration (
  id            text        PRIMARY KEY DEFAULT gen_random_uuid()::text,
  user_id       text        NOT NULL REFERENCES app_user (id),
  tournament_id text        NOT NULL REFERENCES tournament (id),
  nickname      text        NOT NULL CHECK (char_length(nickname) BETWEEN 3 AND 32),
  status        text        NOT NULL CHECK (status IN ('held', 'confirmed', 'expired', 'cancelled')),
  version       bigint      NOT NULL DEFAULT 1 CHECK (version >= 1),
  created_at    timestamptz NOT NULL DEFAULT now(),
  expires_at    timestamptz NOT NULL,
  CHECK (expires_at > created_at)
);

CREATE UNIQUE INDEX registration_one_active
  ON registration (user_id, tournament_id) WHERE status IN ('held', 'confirmed');
CREATE UNIQUE INDEX registration_nickname_active
  ON registration (tournament_id, lower(nickname)) WHERE status IN ('held', 'confirmed');
CREATE INDEX registration_user_list ON registration (user_id, created_at DESC, id DESC);

CREATE TABLE match (
  id            text        PRIMARY KEY DEFAULT gen_random_uuid()::text,
  tournament_id text        NOT NULL REFERENCES tournament (id),
  round         integer     NOT NULL CHECK (round >= 1),
  a_reg_id      text        NOT NULL REFERENCES registration (id),
  b_reg_id      text        NOT NULL REFERENCES registration (id),
  winner_reg_id text        REFERENCES registration (id),
  status        text        NOT NULL DEFAULT 'scheduled' CHECK (status IN ('scheduled', 'finished')),
  finished_at   timestamptz,
  version       bigint      NOT NULL DEFAULT 1 CHECK (version >= 1),
  CHECK (a_reg_id <> b_reg_id),
  CHECK (winner_reg_id IS NULL OR winner_reg_id IN (a_reg_id, b_reg_id)),
  CHECK ((status = 'finished') = (winner_reg_id IS NOT NULL AND finished_at IS NOT NULL))
);
