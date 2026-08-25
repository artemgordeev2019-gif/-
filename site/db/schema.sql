-- Мастерская Гордеева — схема общей базы для Supabase.
--
-- Как применить: Supabase → SQL Editor → New query → вставить всё, Run.
-- Скрипт можно запускать повторно, он не ломает уже существующие данные.

create extension if not exists pgcrypto with schema extensions;

-- ── код доступа ─────────────────────────────────────────────────────────
-- Хранится только хэш. Ни anon, ни залогиненные роли не читают эту таблицу:
-- политик у неё нет, а RLS включён.
create table if not exists public.hb_secret (
  id         boolean primary key default true check (id),
  code_hash  text not null,
  updated_at timestamptz not null default now()
);
alter table public.hb_secret enable row level security;

-- ── данные ──────────────────────────────────────────────────────────────
create table if not exists public.orders (
  id          text primary key,
  title       text not null,
  client      text not null default '',
  category    text not null default '',
  price       numeric not null default 0,
  due         date,
  status      text not null default 'new'  check (status   in ('new','work','review','done')),
  priority    text not null default 'mid'  check (priority in ('high','mid','low')),
  pay         text not null default 'none' check (pay      in ('none','prepay','full')),
  paid_amount numeric not null default 0,
  paid_date   date,
  notes       text not null default '',
  updated_at  timestamptz not null default now()
);

create table if not exists public.personal (
  id         text primary key,
  title      text not null,
  due        date,
  done       boolean not null default false,
  updated_at timestamptz not null default now()
);

alter table public.orders   enable row level security;
alter table public.personal enable row level security;

-- Читать может каждый, кто открыл сайт. Прямой записи нет ни у кого:
-- политик на insert/update/delete не существует, всё идёт через функции ниже.
drop policy if exists "orders readable"   on public.orders;
drop policy if exists "personal readable" on public.personal;
create policy "orders readable"   on public.orders   for select to anon, authenticated using (true);
create policy "personal readable" on public.personal for select to anon, authenticated using (true);

grant usage on schema public to anon, authenticated;
grant select on public.orders, public.personal to anon, authenticated;

-- ── проверка кода ───────────────────────────────────────────────────────
create or replace function public.hb_check(p_code text)
returns void
language plpgsql
security definer
set search_path = public, extensions
as $$
declare h text;
begin
  select code_hash into h from public.hb_secret where id;
  if h is null then
    raise exception 'Код доступа ещё не задан' using errcode = '28000';
  end if;
  if p_code is null or extensions.crypt(p_code, h) <> h then
    raise exception 'Неверный код доступа' using errcode = '28P01';
  end if;
end;
$$;

revoke all on function public.hb_check(text) from public, anon, authenticated;

-- Тихая проверка кода для страницы: true/false без падения.
-- Хэш bcrypt считается медленно, поэтому перебор через неё непрактичен.
create or replace function public.hb_verify(p_code text)
returns boolean
language plpgsql
security definer
set search_path = public, extensions
as $$
declare h text;
begin
  select code_hash into h from public.hb_secret where id;
  if h is null or p_code is null then return false; end if;
  return extensions.crypt(p_code, h) = h;
end;
$$;

revoke all on function public.hb_verify(text) from public;
grant execute on function public.hb_verify(text) to anon, authenticated;

-- ── запись ──────────────────────────────────────────────────────────────
create or replace function public.hb_save_order(p_code text, p_order jsonb)
returns public.orders
language plpgsql
security definer
set search_path = public, extensions
as $$
declare r public.orders;
begin
  perform public.hb_check(p_code);
  if coalesce(p_order->>'title', '') = '' then
    raise exception 'У заказа должно быть название' using errcode = '22000';
  end if;

  insert into public.orders as o (
    id, title, client, category, price, due,
    status, priority, pay, paid_amount, paid_date, notes, updated_at
  ) values (
    coalesce(nullif(p_order->>'id', ''), 'o' || replace(extensions.gen_random_uuid()::text, '-', '')),
    p_order->>'title',
    coalesce(p_order->>'client', ''),
    coalesce(p_order->>'category', ''),
    coalesce((p_order->>'price')::numeric, 0),
    nullif(p_order->>'due', '')::date,
    coalesce(nullif(p_order->>'status', ''), 'new'),
    coalesce(nullif(p_order->>'priority', ''), 'mid'),
    coalesce(nullif(p_order->>'pay', ''), 'none'),
    coalesce((p_order->>'paid_amount')::numeric, 0),
    nullif(p_order->>'paid_date', '')::date,
    coalesce(p_order->>'notes', ''),
    now()
  )
  on conflict (id) do update set
    title       = excluded.title,
    client      = excluded.client,
    category    = excluded.category,
    price       = excluded.price,
    due         = excluded.due,
    status      = excluded.status,
    priority    = excluded.priority,
    pay         = excluded.pay,
    paid_amount = excluded.paid_amount,
    paid_date   = excluded.paid_date,
    notes       = excluded.notes,
    updated_at  = now()
  returning o.* into r;

  return r;
end;
$$;

create or replace function public.hb_delete_order(p_code text, p_id text)
returns void
language plpgsql
security definer
set search_path = public, extensions
as $$
begin
  perform public.hb_check(p_code);
  delete from public.orders where id = p_id;
end;
$$;

create or replace function public.hb_save_task(p_code text, p_task jsonb)
returns public.personal
language plpgsql
security definer
set search_path = public, extensions
as $$
declare r public.personal;
begin
  perform public.hb_check(p_code);
  if coalesce(p_task->>'title', '') = '' then
    raise exception 'У задачи должно быть название' using errcode = '22000';
  end if;

  insert into public.personal as t (id, title, due, done, updated_at)
  values (
    coalesce(nullif(p_task->>'id', ''), 'p' || replace(extensions.gen_random_uuid()::text, '-', '')),
    p_task->>'title',
    nullif(p_task->>'due', '')::date,
    coalesce((p_task->>'done')::boolean, false),
    now()
  )
  on conflict (id) do update set
    title      = excluded.title,
    due        = excluded.due,
    done       = excluded.done,
    updated_at = now()
  returning t.* into r;

  return r;
end;
$$;

create or replace function public.hb_delete_task(p_code text, p_id text)
returns void
language plpgsql
security definer
set search_path = public, extensions
as $$
begin
  perform public.hb_check(p_code);
  delete from public.personal where id = p_id;
end;
$$;

revoke all on function public.hb_save_order(text, jsonb)   from public;
revoke all on function public.hb_delete_order(text, text)  from public;
revoke all on function public.hb_save_task(text, jsonb)    from public;
revoke all on function public.hb_delete_task(text, text)   from public;

grant execute on function public.hb_save_order(text, jsonb)  to anon, authenticated;
grant execute on function public.hb_delete_order(text, text) to anon, authenticated;
grant execute on function public.hb_save_task(text, jsonb)   to anon, authenticated;
grant execute on function public.hb_delete_task(text, text)  to anon, authenticated;

-- ── живые обновления ────────────────────────────────────────────────────
-- replica identity full нужен, чтобы в событии удаления приходил id строки.
alter table public.orders   replica identity full;
alter table public.personal replica identity full;

do $$
begin
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
    if not exists (select 1 from pg_publication_tables
                   where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'orders') then
      alter publication supabase_realtime add table public.orders;
    end if;
    if not exists (select 1 from pg_publication_tables
                   where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'personal') then
      alter publication supabase_realtime add table public.personal;
    end if;
  end if;
end;
$$;
