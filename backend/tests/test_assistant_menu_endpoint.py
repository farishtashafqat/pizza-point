"""Tests for the authenticated, read-only n8n menu feed."""
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.assistant import cheapest_available_offers
from app.main import app


class MenuRepository:
    async def categories(self):
        return [{"id":"cat-1","name":"Pizza","slug":"pizza"},{"id":"cat-2","name":"Burgers","slug":"burgers"},{"id":"cat-3","name":"Drinks","slug":"drinks"}]
    async def catalogue(self):
        return [{
            "id": "pizza-1", "name": "Chicken Pizza", "description": "",
            "base_price": 750, "is_available": True, "is_active": True,
            "category": {"id": "cat-1", "name": "Pizza", "slug": "pizza", "sort_order": 0, "is_active": True},
            "variants": [{"id": "large", "name": "Large 13\"", "price": 1200, "sort_order": 1, "is_active": True}],
        }, {
            "id": "burger-1", "name": "Zinger Burger", "description": "",
            "base_price": 500, "is_available": False, "is_active": True,
            "category": {"id": "cat-2", "name": "Burgers", "slug": "burgers", "sort_order": 1, "is_active": True},
            "variants": [],
        }, {
            "id": "drink-1", "name": "Cola", "description": "",
            "base_price": 120, "is_available": True, "is_active": True,
            "category": {"id": "cat-3", "name": "Drinks", "slug": "drinks", "sort_order": 2, "is_active": True},
            "variants": [],
        }]


class AssistantMenuEndpointTests(unittest.TestCase):
    def setUp(self):
        self.old_key=os.environ.get("ASSISTANT_MENU_API_KEY")
        os.environ["ASSISTANT_MENU_API_KEY"]="test-n8n-secret"
        self.client=TestClient(app)

    def tearDown(self):
        if self.old_key is None:
            os.environ.pop("ASSISTANT_MENU_API_KEY",None)
        else:
            os.environ["ASSISTANT_MENU_API_KEY"]=self.old_key

    def test_rejects_missing_or_invalid_shared_key(self):
        self.assertEqual(self.client.get("/assistant/menu").status_code,401)
        self.assertEqual(self.client.get("/assistant/menu",headers={"X-Assistant-Menu-Key":"wrong"}).status_code,401)

    def request(self, path="/assistant/menu"):
        with patch("app.assistant.Repository",MenuRepository):
            return self.client.get(path,headers={"X-Assistant-Menu-Key":"test-n8n-secret"})

    def test_returns_compact_complete_catalogue_with_availability_when_authenticated(self):
        response=self.request()
        self.assertEqual(response.status_code,200)
        items=response.json()["items"]
        self.assertEqual(len(items),3)
        item=items[0]
        self.assertEqual(item["name"],"Chicken Pizza")
        self.assertTrue(item["available"])
        self.assertEqual(item["category"],"Pizza")
        self.assertEqual(item["variants"][0]["price"],1200)
        self.assertEqual(set(item),{"id","name","category","price","variants","available"})

    def test_category_filter_is_case_insensitive_and_accepts_common_plural_terms(self):
        response=self.request("/assistant/menu?category=BuRgErS")
        self.assertEqual(response.status_code,200)
        self.assertEqual([item["id"] for item in response.json()["items"]],["burger-1"])

    def test_search_matches_real_item_names_and_common_food_keywords(self):
        by_name=self.request("/assistant/menu?search=zInGeR")
        self.assertEqual([item["id"] for item in by_name.json()["items"]],["burger-1"])
        by_keyword=self.request("/assistant/menu?search=pizzas")
        self.assertEqual([item["id"] for item in by_keyword.json()["items"]],["pizza-1"])

    def test_limit_restricts_results_and_safe_max_is_enforced(self):
        limited=self.request("/assistant/menu?limit=2")
        self.assertEqual(len(limited.json()["items"]),2)
        too_large=self.request("/assistant/menu?limit=26")
        self.assertEqual(too_large.status_code,422)

    def test_pagination_metadata_marks_partial_results(self):
        response=self.request("/assistant/menu?limit=2&offset=0")
        self.assertEqual(response.json()|{"items":[]},{"items":[],"total":3,"returned":2,"offset":0,"has_more":True,"next_offset":2})
        response=self.request("/assistant/menu?limit=2&offset=2")
        self.assertFalse(response.json()["has_more"])
        self.assertIsNone(response.json()["next_offset"])

    def test_categories_endpoint_returns_real_category_records(self):
        with patch("app.assistant.Repository",MenuRepository):
            response=self.client.get("/assistant/menu/categories",headers={"X-Assistant-Menu-Key":"test-n8n-secret"})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()["categories"][1]["name"],"Burgers")

    def test_cheapest_endpoint_uses_only_available_purchasable_prices(self):
        with patch("app.assistant.Repository",MenuRepository):
            response=self.client.get("/assistant/menu/cheapest",headers={"X-Assistant-Menu-Key":"test-n8n-secret"})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()["items"],[{"id":"drink-1","name":"Cola","category":"Drinks","variant":None,"price":120}])

    def test_cheapest_category_uses_a_pizza_variant_price(self):
        with patch("app.assistant.Repository",MenuRepository):
            response=self.client.get("/assistant/menu/cheapest?category=pizzas",headers={"X-Assistant-Menu-Key":"test-n8n-secret"})
        self.assertEqual(response.json()["items"][0]["variant"]["name"],"Large 13\"")
        self.assertEqual(response.json()["items"][0]["price"],1200)

    def test_cheapest_excludes_pizza_add_ons_but_keeps_real_pizza_sizes(self):
        category={"name":"Pizza","slug":"pizza","is_active":True}
        items=[
            {"id":"addon","name":"Extra Topping / Cheese Crust","base_price":None,"is_active":True,"is_available":True,"category":category,"variants":[{"id":"addon-small","name":"Small","price":100,"is_active":True}]},
            {"id":"pizza","name":"Chicken Tikka Pizza","base_price":None,"is_active":True,"is_available":True,"category":category,"variants":[{"id":"pizza-small","name":"Small 7\"","price":600,"is_active":True}]},
        ]
        self.assertEqual(cheapest_available_offers(items,"pizza")[0]["id"],"pizza")
