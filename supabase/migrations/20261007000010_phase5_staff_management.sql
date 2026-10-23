-- Phase 5 staff lifecycle. Only backend service-role calls can manage staff.
alter table public.profiles add column if not exists is_active boolean not null default true;
create index if not exists profiles_staff_role_active_idx on public.profiles(role, is_active);

create or replace function public.prevent_profile_role_change()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  if auth.uid() = old.id and (old.role is distinct from new.role or old.is_active is distinct from new.is_active) then
    raise exception 'Role and active status changes are not permitted';
  end if;
  new.updated_at = now();
  return new;
end;
$$;
