-- Phase 5: staff order visibility and state transitions. All writes remain RPC-only.
create or replace function public.is_kitchen()
returns boolean language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.profiles where id = auth.uid() and role = 'kitchen');
$$;

create policy "orders: admin reads all" on public.orders for select to authenticated using (public.is_admin());
create policy "orders: kitchen reads active" on public.orders for select to authenticated using (public.is_kitchen() and status in ('Confirmed','Preparing','Ready'));
create policy "order items: admin reads all" on public.order_items for select to authenticated using (public.is_admin());
create policy "order items: kitchen reads active" on public.order_items for select to authenticated using (exists (select 1 from public.orders o where o.id=order_id and public.is_kitchen() and o.status in ('Confirmed','Preparing','Ready')));

create or replace function public.transition_order_status(p_order_id uuid, p_status text) returns public.orders
language plpgsql security definer set search_path = public as $$
declare v_order public.orders; v_role public.app_role;
begin
  if auth.uid() is null then raise exception 'Authentication required' using errcode='28000'; end if;
  select role into v_role from public.profiles where id=auth.uid();
  select * into v_order from public.orders where id=p_order_id for update;
  if not found then raise exception 'Order not found' using errcode='P0002'; end if;
  if v_role='admin' and ((v_order.status='Pending' and p_status in ('Confirmed','Rejected')) or (v_order.status='Ready' and p_status='Completed')) then
    update public.orders set status=p_status where id=p_order_id returning * into v_order; return v_order;
  end if;
  if v_role='kitchen' and ((v_order.status='Confirmed' and p_status='Preparing') or (v_order.status='Preparing' and p_status='Ready')) then
    update public.orders set status=p_status where id=p_order_id returning * into v_order; return v_order;
  end if;
  raise exception 'This status transition is not permitted' using errcode='42501';
end; $$;

revoke all on function public.transition_order_status(uuid,text) from public;
grant execute on function public.transition_order_status(uuid,text) to authenticated;
