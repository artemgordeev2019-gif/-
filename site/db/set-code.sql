-- Задать (или сменить) общий код доступа.
-- Supabase → SQL Editor → вставить, заменить СЛОВО на свой код, Run.
-- Код нигде не хранится в открытом виде: в базу уходит только bcrypt-хэш.

insert into public.hb_secret (id, code_hash)
values (true, extensions.crypt('СЛОВО', extensions.gen_salt('bf')))
on conflict (id) do update
  set code_hash = excluded.code_hash,
      updated_at = now();
