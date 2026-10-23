-- Phase 2: provisional drinks catalogue.
-- These customer-visible records intentionally remain unavailable until Pizza Point
-- confirms both stock and prices in the admin menu manager.  This migration is
-- safe to re-run and never overwrites an existing item.
insert into public.menu_items (
  category_id,
  name,
  description,
  image_url,
  base_price,
  pamphlet_section,
  is_available,
  is_active
)
select
  category.id,
  drink.name,
  drink.size_label || ' · Availability and price pending restaurant confirmation.',
  null,
  drink.provisional_price,
  'Drinks',
  false,
  true
from (
  values
    ('Pepsi Bottle 500ml', '500 ml', 110::numeric),
    ('Pepsi Can 250ml', '250 ml', 120::numeric),
    ('7UP Bottle 500ml', '500 ml', 110::numeric),
    ('Mountain Dew Bottle 500ml', '500 ml', 110::numeric),
    ('Mirinda Orange 500ml', '500 ml', 110::numeric),
    ('Aquafina Mineral Water 500ml', '500 ml', 55::numeric),
    ('Coca-Cola Bottle 500ml', '500 ml', 100::numeric),
    ('Sting Energy Drink 500ml', '500 ml', 130::numeric)
) as drink(name, size_label, provisional_price)
join public.menu_categories as category on category.slug = 'drinks'
on conflict (category_id, name) do nothing;
