INSERT INTO tournament (id, game, starts_at, slots, available, fee_minor) VALUES
  ('t-race', 'Valorant', '2027-07-03 12:00+03', 64, 64, 5000);

INSERT INTO app_user (id, login, name, password_hash, role)
SELECT 'u-race' || lpad(n::text, 3, '0'),
       'race' || lpad(n::text, 3, '0'),
       'Учасник досліду ' || n,
       crypt('race-pass', gen_salt('bf')),
       'user'
FROM generate_series(1, 200) AS n;
