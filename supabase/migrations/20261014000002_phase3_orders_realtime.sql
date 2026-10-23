-- Phase 3: publish only order-row changes for Supabase Realtime.
-- Existing RLS SELECT policies continue to decide which authenticated user can
-- receive an event. The browser refetches through the existing API afterwards.
alter table public.orders replica identity full;

do $$
begin
  if not exists (
    select 1 from pg_publication_tables
    where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'orders'
  ) then
    alter publication supabase_realtime add table public.orders;
  end if;
end $$;
