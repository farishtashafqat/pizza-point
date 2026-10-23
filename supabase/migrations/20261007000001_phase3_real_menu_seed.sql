-- Pizza Point official menu seed (Phase 3). No image URLs, inferred descriptions,
-- or standalone drink products are included. Safe to re-run without duplicates.
create unique index if not exists menu_items_category_name_key on public.menu_items(category_id, name);

with seed_items(category_slug, name, description, base_price) as (values
  ('pizza','Chicken Tikka Pizza',null,null),('pizza','Chicken Fajita Pizza',null,null),('pizza','Chicken Tandoori Pizza',null,null),('pizza','Chicken Achar Pizza',null,null),
  ('pizza','Pizza Point Special',null,null),('pizza','Malai Botti',null,null),('pizza','Chicken Lover',null,null),('pizza','Donner Pizza',null,null),('pizza','Labnani Pizza',null,null),
  ('pizza','Crown Crust Pizza',null,null),('pizza','Crown Kabab Crust Pizza',null,null),('pizza','Stuff Kabab Pizza',null,null),('pizza','Stuff Cheese Pizza',null,null),('pizza','Extra Topping / Cheese Crust',null,null),
  ('burgers','Zinger Burger',null,300),('burgers','Zinger Burger with Cheese',null,350),('burgers','Chicken Petty Burger',null,250),('burgers','Chicken Petty Burger Cheese',null,300),('burgers','Chicken Tower Burger',null,400),('burgers','Chicken Tower Cheese Burger',null,450),('burgers','Double Decker Cheese Burger',null,500),
  ('shawarma','Chicken Shawarma',null,200),('shawarma','Chicken Cheese Shawarma',null,250),('shawarma','Zinger Shawarma',null,250),('shawarma','Zinger Cheese Shawarma',null,300),('shawarma','Seekh Kabab Shawarma',null,250),('shawarma','Seekh Kabab Cheese Shawarma',null,300),('shawarma','Vegetable Shawarma',null,150),
  ('paratha-rolls','Chicken Paratha',null,250),('paratha-rolls','Chicken Cheese Paratha',null,300),('paratha-rolls','Zinger Paratha',null,300),('paratha-rolls','Zinger Cheese Paratha',null,350),('paratha-rolls','Seekh Kabab Paratha',null,300),('paratha-rolls','Seekh Kabab Cheese Paratha',null,350),
  ('chicken','Chicken Piece',null,250),('chicken','Nuggets 10 Piece',null,600),('chicken','Hot Wings 10 Piece',null,700),
  ('fries-sides','French Fries',null,null),('fries-sides','Loaded Fries',null,null),
  ('pasta','Crispy Crunchy Pasta',null,null),('pasta','Creamy Pasta',null,null),
  ('deals','Deal 1',E'1 Zinger Burger\n1 French Fries\n1 Cold Drink',500),
  ('deals','Deal 2',E'1 Zinger Burger\n1 Chicken Pc\n1 French Fries\n1 Cold Drink',700),
  ('deals','Deal 3',E'1 Zinger Burger\n5 Pcs Hot Wings\n1 French Fries\n1 Cold Drink',800),
  ('deals','Deal 4',E'5 Zinger Burger\n1 Ltr Drink',1600),
  ('deals','Deal 5',E'1 Small Pizza\n1 Zinger Burger\n1 French Fries\n1 Ltr Drink',1400),
  ('deals','Deal 6',E'1 Medium Pizza\n1 Zinger Burger\nLarge French Fries\n1 Ltr Drink',2100),
  ('deals','Deal 7',E'1 Large Pizza\n1 Zinger Burger\nLarge French Fries\n1 Ltr Drink',2300),
  ('deals','Deal 8',E'1 Family Pizza\n3 Zinger Burger\n1 Ltr Drink',2600),
  ('deals','Deal 9',E'Half Broast\n1 Ltr Drink\n1 French Fries',900),
  ('deals','Deal 10',E'1 Family Pizza\n5 Zinger Burger\n1 Large Fries\n1 Ltr Drink',3400),
  ('deals','Deal 11',E'1 Medium Pizza\n2 Zinger Burger\n1 Ltr Drink',1600),
  ('deals','Deal 12',E'1 Large Pizza\n1 Ltr Drink',1400),
  ('deals','Deal 13',E'2 Zinger Burger\n10 Pcs Hot Wings\n1 Ltr Drink',1400),
  ('deals','Deal 14',E'1 Large Pizza\n4 Zinger Burger\n1 Ltr Drink',2600),
  ('deals','Deal 15',E'1 Large Pizza\n2 Zinger Burger\n1 Ltr Drink',2000),
  ('deals','Deal 16',E'Full Broast\n1 French Fries',1400),
  ('deals','Supper Deal 1',E'3 Chicken Tikka Small Pizza\n1 Ltr Drink',1699),
  ('deals','Supper Deal 2',E'3 Chicken Tikka Medium Pizza\n1 Ltr Drink',2699),
  ('deals','Supper Deal 3',E'3 Chicken Tikka Large Pizza\n1.5 Ltr Drink Free',3699),
  ('deals','Supper Deal 4',E'3 Chicken Tikka Family Pizza\n1.5 Ltr Drink Free',4599),
  ('deals','Special Deal',E'2 Zinger Burger\n2 Regular Drink',700)
)
insert into public.menu_items(category_id,name,description,base_price,is_available,is_active)
select c.id,s.name,s.description,s.base_price,true,true from seed_items s join public.menu_categories c on c.slug=s.category_slug
on conflict (category_id,name) do update set description=excluded.description,base_price=excluded.base_price,is_available=true,is_active=true;

with seed_variants(category_slug,item_name,name,price,sort_order) as (values
  ('pizza','Chicken Tikka Pizza','Small 7"',600,10),('pizza','Chicken Tikka Pizza','Medium 10"',950,20),('pizza','Chicken Tikka Pizza','Large 13"',1300,30),('pizza','Chicken Tikka Pizza','Family 16"',1600,40),
  ('pizza','Chicken Fajita Pizza','Small 7"',600,10),('pizza','Chicken Fajita Pizza','Medium 10"',950,20),('pizza','Chicken Fajita Pizza','Large 13"',1300,30),('pizza','Chicken Fajita Pizza','Family 16"',1600,40),
  ('pizza','Chicken Tandoori Pizza','Small 7"',600,10),('pizza','Chicken Tandoori Pizza','Medium 10"',950,20),('pizza','Chicken Tandoori Pizza','Large 13"',1300,30),('pizza','Chicken Tandoori Pizza','Family 16"',1600,40),
  ('pizza','Chicken Achar Pizza','Small 7"',600,10),('pizza','Chicken Achar Pizza','Medium 10"',950,20),('pizza','Chicken Achar Pizza','Large 13"',1300,30),('pizza','Chicken Achar Pizza','Family 16"',1600,40),
  ('pizza','Pizza Point Special','Small 7"',700,10),('pizza','Pizza Point Special','Medium 10"',1050,20),('pizza','Pizza Point Special','Large 13"',1400,30),('pizza','Pizza Point Special','Family 16"',1750,40),
  ('pizza','Malai Botti','Small 7"',700,10),('pizza','Malai Botti','Medium 10"',1050,20),('pizza','Malai Botti','Large 13"',1400,30),('pizza','Malai Botti','Family 16"',1750,40),
  ('pizza','Chicken Lover','Small 7"',700,10),('pizza','Chicken Lover','Medium 10"',1050,20),('pizza','Chicken Lover','Large 13"',1400,30),('pizza','Chicken Lover','Family 16"',1750,40),
  ('pizza','Donner Pizza','Small 7"',700,10),('pizza','Donner Pizza','Medium 10"',1050,20),('pizza','Donner Pizza','Large 13"',1400,30),('pizza','Donner Pizza','Family 16"',1750,40),
  ('pizza','Labnani Pizza','Small 7"',850,10),('pizza','Labnani Pizza','Medium 10"',1400,20),('pizza','Labnani Pizza','Large 13"',1900,30),
  ('pizza','Crown Crust Pizza','Small 7"',800,10),('pizza','Crown Crust Pizza','Medium 10"',1150,20),('pizza','Crown Crust Pizza','Large 13"',1600,30),('pizza','Crown Crust Pizza','Family 16"',1850,40),
  ('pizza','Crown Kabab Crust Pizza','Small 7"',800,10),('pizza','Crown Kabab Crust Pizza','Medium 10"',1150,20),('pizza','Crown Kabab Crust Pizza','Large 13"',1600,30),('pizza','Crown Kabab Crust Pizza','Family 16"',1850,40),
  ('pizza','Stuff Kabab Pizza','Small 7"',800,10),('pizza','Stuff Kabab Pizza','Medium 10"',1150,20),('pizza','Stuff Kabab Pizza','Large 13"',1600,30),('pizza','Stuff Kabab Pizza','Family 16"',1850,40),
  ('pizza','Stuff Cheese Pizza','Small 7"',800,10),('pizza','Stuff Cheese Pizza','Medium 10"',1150,20),('pizza','Stuff Cheese Pizza','Large 13"',1600,30),('pizza','Stuff Cheese Pizza','Family 16"',1850,40),
  ('pizza','Extra Topping / Cheese Crust','Small',100,10),('pizza','Extra Topping / Cheese Crust','Medium',150,20),('pizza','Extra Topping / Cheese Crust','Large',200,30),('pizza','Extra Topping / Cheese Crust','Family',250,40),
  ('fries-sides','French Fries','Regular',150,10),('fries-sides','French Fries','Large',250,20),('fries-sides','Loaded Fries','Small',500,10),('fries-sides','Loaded Fries','Large',800,20),
  ('pasta','Crispy Crunchy Pasta','Small',600,10),('pasta','Crispy Crunchy Pasta','Large',1000,20),('pasta','Creamy Pasta','Small',550,10),('pasta','Creamy Pasta','Large',900,20)
)
insert into public.menu_item_variants(item_id,name,price,sort_order,is_active)
select i.id,s.name,s.price,s.sort_order,true from seed_variants s join public.menu_categories c on c.slug=s.category_slug join public.menu_items i on i.category_id=c.id and i.name=s.item_name
on conflict (item_id,name) do update set price=excluded.price,sort_order=excluded.sort_order,is_active=true;
