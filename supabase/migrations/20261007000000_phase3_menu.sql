-- Pizza Point Phase 3: real menu catalogue and admin-only management.
create table public.menu_categories (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  slug text not null unique check (slug ~ '^[a-z0-9-]+$'),
  sort_order integer not null default 0,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.menu_items (
  id uuid primary key default gen_random_uuid(),
  category_id uuid not null references public.menu_categories(id) on delete restrict,
  name text not null,
  description text,
  image_url text,
  base_price numeric(12,2) check (base_price is null or base_price >= 0),
  is_available boolean not null default true,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.menu_item_variants (
  id uuid primary key default gen_random_uuid(),
  item_id uuid not null references public.menu_items(id) on delete cascade,
  name text not null,
  price numeric(12,2) not null check (price >= 0),
  sort_order integer not null default 0,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(item_id, name)
);

create index menu_items_category_id_idx on public.menu_items(category_id);
create index menu_item_variants_item_id_idx on public.menu_item_variants(item_id);

-- Categories only; no invented Pizza Point products or prices are seeded.
insert into public.menu_categories (name, slug, sort_order) values
  ('Pizza', 'pizza', 10), ('Burgers', 'burgers', 20), ('Shawarma', 'shawarma', 30),
  ('Paratha Rolls', 'paratha-rolls', 40), ('Chicken', 'chicken', 50),
  ('Fries / Sides', 'fries-sides', 60), ('Pasta', 'pasta', 70), ('Drinks', 'drinks', 80),
  ('Deals', 'deals', 90)
on conflict (slug) do nothing;

create or replace function public.is_admin()
returns boolean language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.profiles where id = auth.uid() and role = 'admin');
$$;

create or replace function public.set_menu_updated_at()
returns trigger language plpgsql security definer set search_path = public as $$
begin new.updated_at = now(); return new; end;
$$;

create trigger menu_categories_updated_at before update on public.menu_categories for each row execute procedure public.set_menu_updated_at();
create trigger menu_items_updated_at before update on public.menu_items for each row execute procedure public.set_menu_updated_at();
create trigger menu_item_variants_updated_at before update on public.menu_item_variants for each row execute procedure public.set_menu_updated_at();

alter table public.menu_categories enable row level security;
alter table public.menu_items enable row level security;
alter table public.menu_item_variants enable row level security;

-- Public customers can only see active catalogue data. Admins can see and manage all rows.
create policy "menu categories public active read" on public.menu_categories for select using (is_active or public.is_admin());
create policy "menu items public active read" on public.menu_items for select using (is_active or public.is_admin());
create policy "menu variants public active read" on public.menu_item_variants for select using (is_active or public.is_admin());
create policy "admins manage categories" on public.menu_categories for all to authenticated using (public.is_admin()) with check (public.is_admin());
create policy "admins manage items" on public.menu_items for all to authenticated using (public.is_admin()) with check (public.is_admin());
create policy "admins manage variants" on public.menu_item_variants for all to authenticated using (public.is_admin()) with check (public.is_admin());
