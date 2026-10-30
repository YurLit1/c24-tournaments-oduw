-- Example seed data of "Міська бібліотека" for the demo and the teacher's check: users of both
-- roles and the resources of the examples in openapi.example.yaml (normal b01, scarce b-one).
-- Logins for the check: --user reader=reader1:reader-pass --user reader2=reader2:reader-pass
--                       --user staff=librarian:librarian-pass
-- Password hashes are bcrypt (pgcrypto), readable by bcrypt libraries of any language.
-- Experiments without protection run on separate data (see migrations/README.md).

CREATE EXTENSION IF NOT EXISTS pgcrypto;

INSERT INTO branch (id, name, tz) VALUES
  ('central', 'Центральна бібліотека', 'Europe/Kyiv'),
  ('podil', 'Філія на Подолі', 'Europe/Kyiv');

INSERT INTO book (id, title, author) VALUES
  ('b01', 'Кобзар', 'Тарас Шевченко'),
  ('b02', 'Тигролови', 'Іван Багряний'),
  ('b-one', 'Рідкісне видання', 'Невідомий автор');

INSERT INTO stock (branch_id, book_id, copies_total, copies_available) VALUES
  ('central', 'b01', 1000, 1000),
  ('central', 'b02', 5, 5),
  ('central', 'b-one', 1, 1),
  ('podil', 'b01', 3, 3);

INSERT INTO app_user (id, login, name, password_hash, role) VALUES
  ('u-reader1', 'reader1', 'Олена Коваль', crypt('reader-pass', gen_salt('bf')), 'user'),
  ('u-reader2', 'reader2', 'Андрій Мельник', crypt('reader-pass', gen_salt('bf')), 'user'),
  ('u-librarian', 'librarian', 'Оксана Бондар', crypt('librarian-pass', gen_salt('bf')), 'staff');
