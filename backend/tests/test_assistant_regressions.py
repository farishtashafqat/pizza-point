"""Regression tests for production-shaped assistant failures.

The route test uses an in-memory async Repository: it exercises the actual
FastAPI route function without a network connection or Supabase credentials.
"""
import unittest
from unittest.mock import patch

from app.assistant import AssistantState, DraftLine, Engine, MessageIn, send_message
from app.auth import CurrentProfile


MENU=[
    *[{"id":f"s{i}","name":name,"base_price":price,"category_slug":"shawarma","category_name":"Shawarma","variants":[]} for i,(name,price) in enumerate([
        ("Chicken Shawarma",200),("Chicken Cheese Shawarma",250),("Zinger Shawarma",250),("Zinger Cheese Shawarma",300),("Seekh Kabab Shawarma",250),("Seekh Kabab Cheese Shawarma",300),("Vegetable Shawarma",150)],1)],
    *[{"id":f"b{i}","name":name,"base_price":price,"category_slug":"burgers","category_name":"Burgers","variants":[]} for i,(name,price) in enumerate([
        ("Zinger Burger",300),("Zinger Burger with Cheese",350),("Chicken Petty Burger",250),("Chicken Petty Burger Cheese",300),("Chicken Tower Burger",400),("Chicken Tower Cheese Burger",450),("Double Decker Cheese Burger",500)],1)],
]


class EngineRegressionTests(unittest.TestCase):
    def setUp(self): self.engine=Engine(MENU); self.state=AssistantState()

    def test_budget_roman_urdu_after_pending_never_mutates(self):
        self.engine.respond(self.state,"show shawarma")
        before=self.engine.draft(self.state)
        reply,changed=self.engine.respond(self.state,"300 ke andar kya hai?")
        self.assertFalse(changed); self.assertEqual(self.engine.draft(self.state),before)
        self.assertIn("Vegetable Shawarma",reply); self.assertIn("Rs. 300",reply)

    def test_two_categories_are_complete_and_separate(self):
        reply,changed=self.engine.respond(self.state,"Shawarma aur burger ki alag alag list dikhao.")
        self.assertFalse(changed); self.assertEqual(self.state.lines,[])
        self.assertIn("SHAWARMA".title(),reply); self.assertIn("Burgers",reply)
        self.assertIn("Vegetable Shawarma",reply); self.assertIn("Double Decker Cheese Burger",reply)
        self.assertLess(reply.index("Vegetable Shawarma"),reply.index("Burgers"))

    def test_exact_named_price_beats_cheese_filter(self):
        reply,changed=self.engine.respond(self.state,"Seekh Kabab Cheese Shawarma kitne ka hai?")
        self.assertFalse(changed); self.assertEqual(self.state.lines,[])
        self.assertEqual(reply,"Seekh Kabab Cheese Shawarma is available for Rs. 300.")

    def test_ambiguous_shawarma_add_only_opens_selection(self):
        reply,changed=self.engine.respond(self.state,"Ek shawarma add karo.")
        self.assertTrue(changed); self.assertEqual(self.state.lines,[])
        self.assertEqual(self.state.pending["kind"],"item"); self.assertIn("Vegetable Shawarma",reply)

    def test_pending_questions_and_prices_are_not_selections(self):
        self.engine.respond(self.state,"add shawarma")
        before=self.engine.draft(self.state)
        for message in ("what is cheaper", "300 se kam kya hai?", "show burgers"):
            with self.subTest(message=message):
                _,changed=self.engine.respond(self.state,message)
                self.assertFalse(changed); self.assertEqual(self.engine.draft(self.state),before)


class MemoryRepository:
    state=AssistantState(); stored_messages=[]
    async def session(self, customer_id): return {"id":"session-1","customer_id":customer_id,"pending":None,"context":{},"order_type":None,"delivery_address":None}
    async def menu(self): return MENU
    async def load(self, session): return self.state
    async def messages(self, sid): return self.stored_messages[-50:]
    async def prior_reply(self, sid, message_id): return None
    async def snapshot(self, sid, state): pass
    async def save(self, session, state): self.__class__.state=state
    async def message(self, sid, role, content, client_message_id=None): self.__class__.stored_messages.append({"role":role,"content":content,"created_at":"2026-01-01T00:00:00Z"})

class GroqStub:
    async def hint(self, message, menu, history, draft):
        # Deliberately return an ADD proposal for a question. The centralized
        # gate must reject it because the customer did not explicitly ask to add.
        return {"intent":"ADD_ITEM","mutation_requested":True,"item_id":"s4","quantity":1,"confidence":.99}

class GroqHttp400Stub:
    """Matches GroqIntentService's post-HTTP-400 contract."""
    async def hint(self, message, menu, history, draft):
        return {"provider":"invalid_request"}

class AssistantRouteRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        MemoryRepository.state=AssistantState(); MemoryRepository.stored_messages=[]
        self.profile=CurrentProfile("customer-1","customer@example.com","Customer","customer")

    async def test_authenticated_route_rejects_model_proposed_add_for_budget_question(self):
        with patch("app.assistant.Repository",MemoryRepository), patch("app.assistant.GroqIntentService",GroqStub):
            response=await send_message(MessageIn(message="300 ke andar kya hai?",message_id="m1"),self.profile)
        self.assertEqual(response["draft"]["count"],0)
        self.assertIn("Available under that amount",response["reply"])
        self.assertEqual([x["role"] for x in response["messages"]],["customer","assistant"])

    async def test_http_400_fallback_keeps_named_pizza_order_and_completes_variant(self):
        pizza_menu=[{"id":"lover","name":"Chicken Lover","base_price":None,"category_slug":"pizza","category_name":"Pizza","variants":[{"id":"lover-medium","name":"Medium 10\"","price":1050}]}]
        class PizzaRepository(MemoryRepository):
            async def menu(self): return pizza_menu
        with patch("app.assistant.Repository",PizzaRepository), patch("app.assistant.GroqIntentService",GroqHttp400Stub):
            first=await send_message(MessageIn(message="I want to order Chicken Lover Pizza.",message_id="pizza-1"),self.profile)
            second=await send_message(MessageIn(message="medium",message_id="pizza-2"),self.profile)
        self.assertIn("Which size for Chicken Lover",first["reply"])
        self.assertEqual(first["draft"]["count"],0)
        self.assertIn("Added 1",second["reply"])
        self.assertEqual(second["draft"]["count"],1)

