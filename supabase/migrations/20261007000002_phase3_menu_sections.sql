-- Phase 3: official pamphlet grouping for customer menu presentation.
alter table public.menu_items add column if not exists pamphlet_section text;

update public.menu_items set pamphlet_section = case
  when name in ('Chicken Tikka Pizza','Chicken Fajita Pizza','Chicken Tandoori Pizza','Chicken Achar Pizza') then 'Classic Pizza'
  when name in ('Pizza Point Special','Malai Botti','Chicken Lover','Donner Pizza','Labnani Pizza') then 'Special Pizza'
  when name in ('Crown Crust Pizza','Crown Kabab Crust Pizza','Stuff Kabab Pizza','Stuff Cheese Pizza') then 'Stuff Crust Pizza'
  when name = 'Extra Topping / Cheese Crust' then 'Extra Topping / Cheese Crust'
  when name in ('Zinger Burger','Zinger Burger with Cheese','Chicken Petty Burger','Chicken Petty Burger Cheese','Chicken Tower Burger','Chicken Tower Cheese Burger','Double Decker Cheese Burger') then 'Burgers'
  when name in ('Chicken Shawarma','Chicken Cheese Shawarma','Zinger Shawarma','Zinger Cheese Shawarma','Seekh Kabab Shawarma','Seekh Kabab Cheese Shawarma','Vegetable Shawarma') then 'Shawarma'
  when name in ('Chicken Paratha','Chicken Cheese Paratha','Zinger Paratha','Zinger Cheese Paratha','Seekh Kabab Paratha','Seekh Kabab Cheese Paratha') then 'Paratha Rolls'
  when name in ('Chicken Piece','Nuggets 10 Piece','Hot Wings 10 Piece') then 'Crispy Chicken'
  when name = 'French Fries' then 'French Fries'
  when name = 'Loaded Fries' then 'Loaded Fries'
  when name in ('Crispy Crunchy Pasta','Creamy Pasta') then 'Pasta'
  when name in ('Deal 1','Deal 2','Deal 3','Deal 4','Deal 5','Deal 6','Deal 7','Deal 8','Deal 9','Deal 10') then 'Classic & Student Deals'
  when name in ('Deal 11','Deal 12','Deal 13','Deal 14','Deal 15','Deal 16') then 'Friends & Family Deals'
  when name in ('Supper Deal 1','Supper Deal 2','Supper Deal 3','Supper Deal 4') then 'Triple Pizza / Supper Deals'
  when name = 'Special Deal' then 'Special Deal'
end
where pamphlet_section is null;

alter table public.menu_items alter column pamphlet_section set not null;
