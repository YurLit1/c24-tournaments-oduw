-- Example schema of "Міська бібліотека" (not applied: migrate reads only migrations/NNN_*.sql).
-- Invariant: holds and collected copies never exceed the copies of a branch.

CREATE TABLE branch (
  id   text PRIMARY KEY,
  name text NOT NULL,
  tz   text NOT NULL
);

CREATE TABLE book (
  id     text PRIMARY KEY,
  title  text NOT NULL,
  author text NOT NULL
);

CREATE TABLE stock (
  branch_id        text NOT NULL REFERENCES branch (id),
  book_id          text NOT NULL REFERENCES book (id),
  copies_total     integer NOT NULL CHECK (copies_total >= 0),
  copies_available integer NOT NULL,
  PRIMARY KEY (branch_id, book_id),
  CHECK (copies_available BETWEEN 0 AND copies_total)
);

CREATE TABLE app_user (
  id            text PRIMARY KEY,
  login         text NOT NULL UNIQUE,
  name          text NOT NULL,
  password_hash text NOT NULL,
  role          text NOT NULL CHECK (role IN ('user', 'staff'))
);

CREATE TABLE hold (
  id          text PRIMARY KEY,
  user_id     text NOT NULL REFERENCES app_user (id),
  branch_id   text NOT NULL,
  book_id     text NOT NULL,
  pickup_name text,
  status      text NOT NULL CHECK (status IN ('held', 'collected', 'returned', 'expired', 'cancelled')),
  version     bigint NOT NULL DEFAULT 1,
  created_at  timestamptz NOT NULL DEFAULT now(),
  expires_at  timestamptz NOT NULL,
  FOREIGN KEY (branch_id, book_id) REFERENCES stock (branch_id, book_id)
);

-- one active hold per reader and book
CREATE UNIQUE INDEX hold_one_active_per_book ON hold (user_id, book_id) WHERE status = 'held';
