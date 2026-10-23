-- Phase 6A assistant draft state. These rows are never real orders.
create table public.assistant_sessions (
  id uuid primary key default gen_random_uuid(), customer_id uuid not null references public.profiles(id) on delete cascade,
  pending jsonb, context jsonb not null default '{}'::jsonb, order_type text check (order_type in ('delivery','pickup')), delivery_address text,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(customer_id)
);
create table public.assistant_draft_items (
  id uuid primary key default gen_random_uuid(), session_id uuid not null references public.assistant_sessions(id) on delete cascade,
  menu_item_id uuid not null references public.menu_items(id) on delete restrict, variant_id uuid references public.menu_item_variants(id) on delete restrict,
  quantity integer not null check (quantity between 1 and 99), created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(session_id,menu_item_id,variant_id)
);
create table public.assistant_actions (
  id uuid primary key default gen_random_uuid(), session_id uuid not null references public.assistant_sessions(id) on delete cascade,
  action jsonb not null, created_at timestamptz not null default now()
);
create table public.assistant_messages (
  id uuid primary key default gen_random_uuid(), session_id uuid not null references public.assistant_sessions(id) on delete cascade,
  role text not null check (role in ('customer','assistant')), client_message_id text, content text not null check (char_length(content) between 1 and 2000),
  created_at timestamptz not null default now()
);
create unique index assistant_messages_dedupe_idx on public.assistant_messages(session_id, client_message_id) where client_message_id is not null;
create trigger assistant_sessions_updated_at before update on public.assistant_sessions for each row execute procedure public.set_menu_updated_at();
create trigger assistant_draft_items_updated_at before update on public.assistant_draft_items for each row execute procedure public.set_menu_updated_at();
alter table public.assistant_sessions enable row level security; alter table public.assistant_draft_items enable row level security; alter table public.assistant_actions enable row level security; alter table public.assistant_messages enable row level security;
create policy "assistant sessions: own read" on public.assistant_sessions for select to authenticated using (customer_id=(select auth.uid()));
create policy "assistant draft: own read" on public.assistant_draft_items for select to authenticated using (exists(select 1 from public.assistant_sessions s where s.id=session_id and s.customer_id=(select auth.uid())));
create policy "assistant actions: own read" on public.assistant_actions for select to authenticated using (exists(select 1 from public.assistant_sessions s where s.id=session_id and s.customer_id=(select auth.uid())));
create policy "assistant messages: own read" on public.assistant_messages for select to authenticated using (exists(select 1 from public.assistant_sessions s where s.id=session_id and s.customer_id=(select auth.uid())));
