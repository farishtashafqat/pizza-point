# Pizza Point — Phase 2

Pizza Point is a React/TypeScript customer interface with a FastAPI API. Phase 2 adds Supabase Authentication and secure role-based access. The app still uses mock menu/cart content only: real orders, menus, payments, AI, WhatsApp, and analytics are intentionally not included.

## Phase 3 menu catalogue

Run [20261007000000_phase3_menu.sql](supabase/migrations/20261007000000_phase3_menu.sql) in the Supabase SQL editor after the Phase 2 migration. It creates the real menu catalogue tables (`menu_categories`, `menu_items`, and `menu_item_variants`), seeds only the approved categories, and enables RLS. It does not insert made-up food items, prices, or images.

After applying that schema migration, run [20261007000001_phase3_real_menu_seed.sql](supabase/migrations/20261007000001_phase3_real_menu_seed.sql). It idempotently seeds the official Pizza Point catalogue supplied for Phase 3, including deal contents and size-based prices. It leaves all product image URLs empty and can be re-run without duplicating records.

Run [20261007000002_phase3_menu_sections.sql](supabase/migrations/20261007000002_phase3_menu_sections.sql) after the real-menu seed. It adds the official pamphlet presentation section to every seeded item so `/menu` displays Pizza, Fast Food, and Deals in their supplied subsection order.

## Phase 2 premium drinks catalogue

Run [20261014000000_phase2_provisional_drinks.sql](supabase/migrations/20261014000000_phase2_provisional_drinks.sql) after the menu schema and section migrations. It adds eight named drink records to the existing `Drinks` category with the supplied **provisional** prices. Every new item is active but unavailable, so it is shown as unavailable and cannot be added to a cart, ordered, or returned as purchasable by the assistant. The migration is idempotent and never overwrites an existing drink. An Admin must confirm stock and pricing, then mark an item Available in `/admin` before it can be sold.

After the drinks records exist, run [20261014000001_phase2_drink_images.sql](supabase/migrations/20261014000001_phase2_drink_images.sql). It connects the eight local WebP files in `frontend/public/images/drinks/` to those existing records. It updates image URLs only; prices, availability, and every other product field remain unchanged.

## Phase 3 real-time order synchronization

Run [20261014000002_phase3_orders_realtime.sql](supabase/migrations/20261014000002_phase3_orders_realtime.sql) after the existing order workflow migrations. It adds only `orders` to the `supabase_realtime` publication and is safe to re-run. Existing RLS policies remain unchanged: customers subscribe only to their own `customer_id`, kitchen receives its active permitted orders, and admins receive their already-authorized order stream. Realtime events are not used as data; the frontend refetches the existing authenticated FastAPI endpoint after each event or reconnect.

Run [20261007000003_phase3_deal_images.sql](supabase/migrations/20261007000003_phase3_deal_images.sql) after the menu seed to connect the generated deal artwork in `frontend/public/menu/deals/` to each deal card.

For an existing catalogue that already ran the earlier deal-image migration, run [20261007000004_generated_deal_images.sql](supabase/migrations/20261007000004_generated_deal_images.sql) to switch its image URLs to the generated artwork.

The `/menu` page reads only from Supabase. Signed-in Admins can manage categories, items, availability, image URLs, base prices, and size/variant prices at `/admin`. Database RLS permits catalogue writes only to the Admin role; Kitchen and Customer accounts cannot change menu data even by calling Supabase directly.

## Phase 4 ordering

Run [20261007000005_phase4_orders.sql](supabase/migrations/20261007000005_phase4_orders.sql) after the Phase 2 and Phase 3 migrations. It creates private customer orders/order items and the transactional order and cancellation RPCs. Orders are placed through FastAPI, so start the backend alongside the frontend (`npm run backend`). Add `VITE_API_URL=http://localhost:8000` to `frontend/.env` when using the local API.

If Phase 4 was already applied, also run [20261007000006_phase4_phone_validation.sql](supabase/migrations/20261007000006_phase4_phone_validation.sql) to add the normalized Pakistani-mobile constraint.

## Menu images

Run [20261007000007_menu_item_images.sql](supabase/migrations/20261007000007_menu_item_images.sql) to connect the generated non-deal menu photography in `frontend/public/menu/items/`. It updates only the listed non-deal items and preserves every existing deal image.

Run [20261007000008_distinct_menu_item_images.sql](supabase/migrations/20261007000008_distinct_menu_item_images.sql) after it to replace the shared non-deal images with item-specific photography; it also leaves existing deal images untouched.

## Phase 5 order workflow

Run [20261007000009_phase5_order_workflow.sql](supabase/migrations/20261007000009_phase5_order_workflow.sql) after the Phase 4 migrations. It grants role-scoped staff order reads and creates the database-enforced Admin/Kitchen status transition workflow.

Run [20261007000010_phase5_staff_management.sql](supabase/migrations/20261007000010_phase5_staff_management.sql) to add staff active-status enforcement. Add `SUPABASE_SERVICE_ROLE_KEY` only to `backend/.env`; it is required for Admin-only staff invitations and is never used by the frontend.

## Phase 6A grounded draft assistant

Run [20261007000011_phase6a_assistant.sql](supabase/migrations/20261007000011_phase6a_assistant.sql) after the existing migrations. It creates customer-private assistant sessions, draft-cart items, undo snapshots, and conversation messages. These are **not** `orders` and cannot create a real order in Phase 6A. RLS permits a customer to read only their own assistant data; all writes are performed by the authenticated FastAPI service.

Set these backend-only values in `backend/.env`:

```text
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
GROQ_API_KEY=your-groq-key
GROQ_MODEL=openai/gpt-oss-20b
```

`GROQ_API_KEY` is backend-only and required for the intelligent assistant. Groq receives only the live menu snapshot, recent conversation history, and draft context—never database credentials—and never determines prices, availability, totals, or mutations. If Groq is unavailable, the assistant explicitly reports that its intelligent service is unavailable and does not modify the draft. `VITE_API_URL=http://127.0.0.1:8000` remains the only frontend API setting; do not put either backend key in the frontend.

### n8n menu feed

Set a long, random `ASSISTANT_MENU_API_KEY` in `backend/.env`. n8n can read the complete catalogue with `GET http://127.0.0.1:8000/assistant/menu` and the header `X-Assistant-Menu-Key: <ASSISTANT_MENU_API_KEY>`. Use optional, case-insensitive `category`, `search`, and `limit` parameters to minimize AI context, for example `/assistant/menu?category=pizzas&limit=10` or `/assistant/menu?search=zinger&limit=5`. `limit` is capped at 25. Each compact result contains only its ID, name, category, base price, active variants and their prices, and a purchasable availability flag. If an item has variants, use its selected variant's price, matching the ordering flow. This endpoint is read-only and never returns any Supabase credential.

## Supabase setup (required before live authentication)

1. Create a Supabase project and copy its Project URL and anon/publishable key.
2. Run [the Phase 2 migration](supabase/migrations/20261005000000_phase2_auth_profiles.sql) in the Supabase SQL editor. It creates profiles, customer-only signup, RLS, and role-change protection.
3. Copy `frontend/.env.example` to `frontend/.env`; set `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY`.
4. Copy `backend/.env.example` to `backend/.env`; set `SUPABASE_URL` and `SUPABASE_ANON_KEY`. Before starting FastAPI in PowerShell: `Get-Content backend/.env | ForEach-Object { if ($_ -match '^(.*?)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] } }`.
5. Configure Supabase Auth email confirmation and site/redirect URLs. The UI asks users to confirm email if sign-up returns no active session.

Public signup creates **customer** accounts only. To create a test staff account, create the Auth user through the Supabase Dashboard, then use controlled SQL such as `update public.profiles set role = 'kitchen' where email = 'staff@example.com';`. Never expose this capability in public UI.

## Run locally

Frontend (Node 20+):
```powershell
cd frontend
npm install
npm run dev
```
Open http://localhost:5173.

Backend (Python 3.10+):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
uvicorn app.main:app --app-dir backend --reload
```
API health: http://127.0.0.1:8000/health

Build the frontend with `npm --prefix frontend run build`.

## Auth test endpoints

Pass a valid Supabase access token as `Authorization: Bearer <token>` to `/auth/me`, `/auth/customer-test`, `/auth/kitchen-test`, or `/auth/admin-test`. Missing/invalid tokens return 401. Correctly authenticated users without the required staff role receive 403.
