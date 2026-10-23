-- Pizza Point Phase 2: identity and role foundation.
create type public.app_role as enum ('customer', 'kitchen', 'admin');

create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text not null,
  full_name text not null default '',
  role public.app_role not null default 'customer',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.profiles enable row level security;

-- A browser can only ever retrieve its own profile.
create policy "profiles: read own" on public.profiles for select
  to authenticated using ((select auth.uid()) = id);

-- Safe customer fields only: this policy plus the trigger below prevents role changes.
create policy "profiles: update own safe fields" on public.profiles for update
  to authenticated using ((select auth.uid()) = id)
  with check ((select auth.uid()) = id);

-- Public signup cannot choose a role. The trigger runs under definer privileges,
-- and reads the name only from auth metadata supplied at registration.
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, email, full_name, role)
  values (new.id, coalesce(new.email, ''), coalesce(new.raw_user_meta_data ->> 'full_name', ''), 'customer');
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users for each row execute procedure public.handle_new_user();

-- Even if a user reaches an update endpoint directly, their role cannot change.
create or replace function public.prevent_profile_role_change()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  if old.role is distinct from new.role and auth.uid() = old.id then
    raise exception 'Role changes are not permitted';
  end if;
  new.updated_at = now();
  return new;
end;
$$;

create trigger prevent_profile_role_change
  before update on public.profiles for each row execute procedure public.prevent_profile_role_change();

-- Deliberately no insert/delete policies: profile creation is trigger-only.
-- Grant staff roles only using a controlled Dashboard/SQL process, never public UI.
