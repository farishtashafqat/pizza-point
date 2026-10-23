-- Phase 2: local, customer-supplied drink photography.
-- This updates only the image URL of the eight existing drinks; it never creates
-- a product or alters pricing, availability, variants, or active status.
with images(item_name, image_url) as (values
  ('Pepsi Bottle 500ml', '/images/drinks/pepsi-bottle.webp'),
  ('Pepsi Can 250ml', '/images/drinks/pepsi-can.webp'),
  ('7UP Bottle 500ml', '/images/drinks/7up-bottle.webp'),
  ('Mountain Dew Bottle 500ml', '/images/drinks/mountain-dew-bottle.webp'),
  ('Mirinda Orange 500ml', '/images/drinks/mirinda-orange.webp'),
  ('Aquafina Mineral Water 500ml', '/images/drinks/aquafina-water.webp'),
  ('Coca-Cola Bottle 500ml', '/images/drinks/coca-cola-bottle.webp'),
  ('Sting Energy Drink 500ml', '/images/drinks/sting-energy-drink.webp')
)
update public.menu_items as item
set image_url = images.image_url
from images
join public.menu_categories as category on category.slug = 'drinks'
where item.category_id = category.id
  and item.name = images.item_name;
