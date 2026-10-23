"""Offline contract checks for Phase 4 request validation and SQL safeguards."""
import unittest
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from app.main import app
from app.orders import CreateOrderRequest, order_response


def payload(**changes):
    data = {"order_type": "delivery", "customer_name": "A Customer", "phone": "03001234567", "delivery_address": "Pizza Street", "notes": None, "payment_method": "cash_on_delivery", "idempotency_key": str(uuid4()), "items": [{"menu_item_id": str(uuid4()), "quantity": 2}]}
    data.update(changes)
    return data


class OrderContractTests(unittest.TestCase):
    def test_delivery_checkout_contract(self):
        order = CreateOrderRequest(**payload())
        self.assertEqual(order.order_type, "delivery")

    def test_pickup_checkout_contract(self):
        order = CreateOrderRequest(**payload(order_type="pickup", delivery_address=None, payment_method="pay_at_restaurant"))
        self.assertEqual(order.payment_method, "pay_at_restaurant")

    def test_invalid_delivery_and_quantity_rejected(self):
        with self.assertRaises(ValidationError): CreateOrderRequest(**payload(delivery_address=""))
        with self.assertRaises(ValidationError): CreateOrderRequest(**payload(items=[{"menu_item_id": str(uuid4()), "quantity": 0}]))

    def test_pakistani_mobile_numbers_are_normalized_and_invalid_formats_rejected(self):
        self.assertEqual(CreateOrderRequest(**payload(phone="+923001234567")).phone, "03001234567")
        self.assertEqual(CreateOrderRequest(**payload(phone="03001234567")).phone, "03001234567")
        for phone in ("923001234567", "031234567890", "03123abc789", "123456789012"):
            with self.assertRaises(ValidationError): CreateOrderRequest(**payload(phone=phone))

    def test_database_contract_has_trusted_price_duplicate_and_privacy_controls(self):
        sql = (Path(__file__).resolve().parents[2] / "supabase/migrations/20261007000005_phase4_orders.sql").read_text()
        for required in ("unique (customer_id, idempotency_key)", "from public.menu_items", "v_price := v_variant.price", "orders: customers read own", "status in ('Pending','Confirmed')"):
            self.assertIn(required, sql)

    def test_post_route_is_the_real_order_handler_and_response_shape_is_checked(self):
        route = next(route for route in app.routes if getattr(route, "path", None) == "/orders" and "POST" in getattr(route, "methods", set()))
        self.assertEqual(route.endpoint.__name__, "create_order")
        self.assertEqual(order_response([{"id":"id","order_number":1,"total":10,"order_type":"pickup","status":"Pending"}])["order_number"], 1)

    def test_phase_five_workflow_is_role_scoped_and_terminal_safe(self):
        sql = (Path(__file__).resolve().parents[2] / "supabase/migrations/20261007000009_phase5_order_workflow.sql").read_text()
        for required in ("v_order.status='Pending' and p_status in ('Confirmed','Rejected')", "v_order.status='Ready' and p_status='Completed'", "v_order.status='Confirmed' and p_status='Preparing'", "v_order.status='Preparing' and p_status='Ready'", "orders: admin reads all", "orders: kitchen reads active"):
            self.assertIn(required, sql)

    def test_staff_lifecycle_migration_blocks_self_service_privilege_changes(self):
        sql = (Path(__file__).resolve().parents[2] / "supabase/migrations/20261007000010_phase5_staff_management.sql").read_text()
        self.assertIn("is_active boolean not null default true", sql)
        self.assertIn("old.is_active is distinct from new.is_active", sql)

    def test_provisional_drinks_seed_is_idempotent_and_unavailable(self):
        sql = (Path(__file__).resolve().parents[2] / "supabase/migrations/20261014000000_phase2_provisional_drinks.sql").read_text()
        expected = (
            "Pepsi Bottle 500ml", "Pepsi Can 250ml", "7UP Bottle 500ml",
            "Mountain Dew Bottle 500ml", "Mirinda Orange 500ml",
            "Aquafina Mineral Water 500ml", "Coca-Cola Bottle 500ml",
            "Sting Energy Drink 500ml",
        )
        for name in expected:
            self.assertIn(name, sql)
        self.assertIn("category.slug = 'drinks'", sql)
        self.assertIn("on conflict (category_id, name) do nothing", sql)
        self.assertIn("false,\n  true", sql)
        self.assertIn("('Pepsi Can 250ml', '250 ml', 120::numeric)", sql)

    def test_drink_images_migration_updates_only_existing_drink_image_urls(self):
        sql = (Path(__file__).resolve().parents[2] / "supabase/migrations/20261014000001_phase2_drink_images.sql").read_text()
        image_paths = (
            "pepsi-bottle.webp", "pepsi-can.webp", "7up-bottle.webp",
            "mountain-dew-bottle.webp", "mirinda-orange.webp",
            "aquafina-water.webp", "coca-cola-bottle.webp",
            "sting-energy-drink.webp",
        )
        for path in image_paths:
            self.assertIn(f"/images/drinks/{path}", sql)
        self.assertIn("category.slug = 'drinks'", sql)
        self.assertIn("update public.menu_items", sql)
        self.assertNotIn("insert into public.menu_items", sql)
        self.assertNotIn("is_available", sql)
        self.assertNotIn("base_price", sql)

    def test_orders_realtime_migration_preserves_rls_and_is_idempotent(self):
        sql = (Path(__file__).resolve().parents[2] / "supabase/migrations/20261014000002_phase3_orders_realtime.sql").read_text()
        self.assertIn("alter table public.orders replica identity full", sql)
        self.assertIn("pg_publication_tables", sql)
        self.assertIn("alter publication supabase_realtime add table public.orders", sql)
        self.assertNotIn("disable row level security", sql)
        self.assertNotIn("create policy", sql)


if __name__ == "__main__":
    unittest.main()
