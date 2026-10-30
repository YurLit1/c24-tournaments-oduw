CREATE EXTENSION IF NOT EXISTS pgcrypto;

INSERT INTO app_user (id, login, name, password_hash, role) VALUES
  ('u-player1', 'player1', 'Гравець 1', crypt('player-pass', gen_salt('bf')), 'user'),
  ('u-player2', 'player2', 'Гравець 2', crypt('player-pass', gen_salt('bf')), 'user'),
  ('u-player3', 'player3', 'Гравець 3', crypt('player-pass', gen_salt('bf')), 'user'),
  ('u-organizer', 'organizer', 'Організатор', crypt('organizer-pass', gen_salt('bf')), 'staff');

INSERT INTO tournament (id, game, starts_at, slots, available, fee_minor) VALUES
  ('t-dota', 'Dota 2', '2027-06-05 12:00+03', 64, 64, 5000),
  ('t-cs2',  'CS2',    '2027-06-12 12:00+03',  2,  2,    0);
