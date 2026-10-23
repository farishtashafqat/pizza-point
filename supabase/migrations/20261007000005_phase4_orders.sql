-- Phase 4: customer orders. Prices and availability are re-checked in the
-- transactional RPC; browser-provided prices and totals are never accepted.
create table public.orders (
  id uuid primary key default gen_random_uuid(),
  order_number bigint generated always as identity unique,
  customer_id uuid not null references public.profiles(id) on delete restrict,
  order_type text not null check (order_type in ('delivery', 'pickup')),
  customer_name text not null,
  phone text not null constraint orders_pakistani_mobile_check check (phone ~ '^03[0-9]{9}$'),
  delivery_address text,
  notes text,
  payment_method text not null check (payment_method in ('cash_on_delivery', 'pay_at_restaurant')),
  status text not null default 'Pending' check (status in ('Pending', 'Confirmed', 'Preparing', 'Ready', 'Completed', 'Rejected', 'Cancelled')),
  total numeric(12,2) not null check (total >= 0),
  idempotency_key uuid not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (customer_id, idempotency_key),
  check ((order_type = 'delivery' and payment_method = 'cash_on_delivery' and delivery_address is not null) or (order_type = 'pickup' and payment_method = 'pay_at_restaurant' and delivery_address is null))
);

create table public.order_items (
  id uuid primary key default gen_random_uuid(),
  order_id uuid not null references public.orders(id) on delete cascade,
  menu_item_id uuid not null references public.menu_items(id) on delete restrict,
  variant_id uuid references public.menu_item_variants(id) on delete restrict,
  item_name text not null,
  variant_name text,
  quantity integer not null check (quantity between 1 and 99),
  unit_price numeric(12,2) not null check (unit_price >= 0),
  line_total numeric(12,2) not null check (line_total >= 0),
  created_at timestamptz not null default now()
);

create index orders_customer_created_idx on public.orders(customer_id, created_at desc);
create index order_items_order_idx on public.order_items(order_id);
create trigger orders_updated_at before update on public.orders for each row execute procedure public.set_menu_updated_at();

alter table public.orders enable row level security;
alter table public.order_items enable row level security;
create policy "orders: customers read own" on public.orders for select to authenticated using ((select auth.uid()) = customer_id);
create policy "order items: customers read own" on public.order_items for select to authenticated using (exists (select 1 from public.orders o where o.id = order_id and o.customer_id = (select auth.uid())));

create or replace function public.create_customer_order(
  p_order_type text, p_customer_name text, p_phone text, p_delivery_address text,
  p_notes text, p_payment_method text, p_idempotency_key uuid, p_items jsonb
) returns public.orders
language plpgsql security definer set search_path = public as $$
declare v_order public.orders; v_line jsonb; v_item public.menu_items; v_variant public.menu_item_variants;
declare v_quantity integer; v_price numeric(12,2); v_total numeric(12,2) := 0; v_count integer := 0;
begin
  if auth.uid() is null then raise exception 'Authentication required' using errcode = '28000'; end if;
  if not exists (select 1 from public.profiles where id = auth.uid() and role = 'customer') then raise exception 'Customer account required' using errcode = '42501'; end if;
  if p_order_type not in ('delivery','pickup') or p_payment_method not in ('cash_on_delivery','pay_at_restaurant') then raise exception 'Invalid order type or payment method'; end if;
  if p_order_type = 'delivery' and (nullif(btrim(coalesce(p_delivery_address,'')),'') is null or p_payment_method <> 'cash_on_delivery') then raise exception 'Delivery address and cash on delivery are required'; end if;
  if p_order_type = 'pickup' and p_payment_method <> 'pay_at_restaurant' then raise exception 'Pickup orders are paid at restaurant'; end if;
  if nullif(btrim(coalesce(p_customer_name,'')),'') is null or nullif(btrim(coalesce(p_phone,'')),'') is null then raise exception 'Customer name and phone are required'; end if;
  select * into v_order from public.orders where customer_id = auth.uid() and idempotency_key = p_idempotency_key;
  if found then return v_order; end if;
  if jsonb_typeof(p_items) <> 'array' or jsonb_array_length(p_items) not between 1 and 50 then raise exception 'Cart must contain between 1 and 50 items'; end if;
  for v_line in select value from jsonb_array_elements(p_items) loop
    v_count := v_count + 1; v_quantity := nullif(v_line->>'quantity','')::integer;
    if v_quantity is null or v_quantity not between 1 and 99 then raise exception 'Invalid quantity'; end if;
    select * into v_item from public.menu_items where id = (v_line->>'menu_item_id')::uuid and is_active and is_available;
    if not found then raise exception 'An item is unavailable'; end if;
    if nullif(v_line->>'variant_id','') is not null then
      select * into v_variant from public.menu_item_variants where id = (v_line->>'variant_id')::uuid and item_id = v_item.id and is_active;
      if not found then raise exception 'A selected size is unavailable'; end if;
      v_price := v_variant.price;
    else
      if exists (select 1 from public.menu_item_variants where item_id = v_item.id and is_active) then raise exception 'A size selection is required'; end if;
      if v_item.base_price is null then raise exception 'Item price is unavailable'; end if;
      v_price := v_item.base_price; v_variant := null;
    end if;
    v_total := v_total + (v_price * v_quantity);
  end loop;
  insert into public.orders(customer_id, order_type, customer_name, phone, delivery_address, notes, payment_method, total, idempotency_key)
  values (auth.uid(), p_order_type, btrim(p_customer_name), btrim(p_phone), case when p_order_type='delivery' then btrim(p_delivery_address) else null end, nullif(btrim(coalesce(p_notes,'')),''), p_payment_method, v_total, p_idempotency_key)
  returning * into v_order;
  for v_line in select value from jsonb_array_elements(p_items) loop
    v_quantity := (v_line->>'quantity')::integer;
    select * into v_item from public.menu_items where id = (v_line->>'menu_item_id')::uuid;
    if nullif(v_line->>'variant_id','') is not null then select * into v_variant from public.menu_item_variants where id = (v_line->>'variant_id')::uuid; v_price := v_variant.price;
    else v_variant := null; v_price := v_item.base_price; end if;
    insert into public.order_items(order_id, menu_item_id, variant_id, item_name, variant_name, quantity, unit_price, line_total)
    values (v_order.id, v_item.id, v_variant.id, v_item.name, v_variant.name, v_quantity, v_price, v_price * v_quantity);
  end loop;
  return v_order;
end; $$;

create or replace function public.cancel_customer_order(p_order_id uuid) returns public.orders
language plpgsql security definer set search_path = public as $$
declare v_order public.orders;
begin
  if auth.uid() is null then raise exception 'Authentication required' using errcode = '28000'; end if;
  if not exists (select 1 from public.profiles where id = auth.uid() and role = 'customer') then raise exception 'Customer account required' using errcode = '42501'; end if;
  update public.orders set status = 'Cancelled' where id = p_order_id and customer_id = auth.uid() and status in ('Pending','Confirmed') returning * into v_order;
  if not found then raise exception 'This order can no longer be cancelled'; end if;
  return v_order;
end; $$;

revoke all on function public.create_customer_order(text,text,text,text,text,text,uuid,jsonb) from public;
revoke all on function public.cancel_customer_order(uuid) from public;
grant execute on function public.create_customer_order(text,text,text,text,text,text,uuid,jsonb) to authenticated;
grant execute on function public.cancel_customer_order(uuid) to authenticated;
