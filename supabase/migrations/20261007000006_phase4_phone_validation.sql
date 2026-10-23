-- Apply after the original Phase 4 migration on existing projects.
do $$ begin
  if not exists (select 1 from pg_constraint where conname = 'orders_pakistani_mobile_check' and conrelid = 'public.orders'::regclass) then
    alter table public.orders add constraint orders_pakistani_mobile_check check (phone ~ '^03[0-9]{9}$');
  end if;
end $$;
