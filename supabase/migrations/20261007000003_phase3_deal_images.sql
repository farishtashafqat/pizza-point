-- Generated deal artwork for the seeded Deals records only.
with images(name, image_url) as (values
  ('Deal 1','/menu/deals/deal-1.png'),('Deal 2','/menu/deals/deal-2.png'),('Deal 3','/menu/deals/deal-3.png'),('Deal 4','/menu/deals/deal-4.png'),
  ('Deal 5','/menu/deals/deal-5.png'),('Deal 6','/menu/deals/deal-6.png'),('Deal 7','/menu/deals/deal-7.png'),('Deal 8','/menu/deals/deal-8.png'),
  ('Deal 9','/menu/deals/deal-9.png'),('Deal 10','/menu/deals/deal-10.png'),('Deal 11','/menu/deals/deal-11.png'),('Deal 12','/menu/deals/deal-12.png'),
  ('Deal 13','/menu/deals/deal-13.png'),('Deal 14','/menu/deals/deal-14.png'),('Deal 15','/menu/deals/deal-15.png'),('Deal 16','/menu/deals/deal-16.png'),
  ('Supper Deal 1','/menu/deals/supper-deal-1.png'),('Supper Deal 2','/menu/deals/supper-deal-2.png'),('Supper Deal 3','/menu/deals/supper-deal-3.png'),('Supper Deal 4','/menu/deals/supper-deal-4.png'),
  ('Special Deal','/menu/deals/special-deal.png')
)
UPDATE public.menu_items AS item
SET image_url = images.image_url
FROM images, public.menu_categories AS category
WHERE category.id = item.category_id
  AND category.slug = 'deals'
  AND item.name = images.name;
