import asyncio
import json
import os
import unittest
from uuid import uuid4
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from pydantic import ValidationError

from app.auth import CurrentProfile
from app.n8n_bridge import CartLine, ChatRequest, HistoryLine, N8nAction, N8nReply, action_matches_explicit_request, action_payload, cart_reply, cheapest_reply, message, normalize_currency, retry_safe, session_id_for, trusted_menu_reply

class FakeResponse:
    def __init__(self,status_code=200,payload=None,content_type="application/json"):
        self.status_code=status_code; self.payload=payload if payload is not None else {"reply":"Hello","action":None}; self.headers={"content-type":content_type}
    def json(self):
        if isinstance(self.payload,Exception): raise self.payload
        return self.payload


class N8nBridgeContractTests(unittest.TestCase):
    def setUp(self):
        self.profile=CurrentProfile("customer-1","a@example.com","A","customer"); self.message_id=uuid4()
        self.old_url=os.environ.get("N8N_CHAT_WEBHOOK_URL"); self.old_secret=os.environ.get("N8N_WEBHOOK_SECRET")
        os.environ["N8N_CHAT_WEBHOOK_URL"]="http://n8n.test/webhook"; os.environ["N8N_WEBHOOK_SECRET"]="test-secret"

    def tearDown(self):
        if self.old_url is None: os.environ.pop("N8N_CHAT_WEBHOOK_URL",None)
        else: os.environ["N8N_CHAT_WEBHOOK_URL"]=self.old_url
        if self.old_secret is None: os.environ.pop("N8N_WEBHOOK_SECRET",None)
        else: os.environ["N8N_WEBHOOK_SECRET"]=self.old_secret

    def test_action_ids_are_stable_for_retries(self):
        action=N8nAction(type="ADD_ITEM",item_id=uuid4(),variant_id=uuid4(),quantity=2)
        self.assertEqual(action_payload(action,self.profile,self.message_id),action_payload(action,self.profile,self.message_id))

    def test_schema_rejects_invalid_cart_actions(self):
        with self.assertRaises(ValidationError): N8nAction(type="ADD_ITEM",item_id=uuid4(),quantity=0)
        with self.assertRaises(ValidationError): N8nAction(type="GET_CART",item_id=uuid4())

    def test_cart_mutations_require_matching_explicit_customer_language(self):
        item_id=uuid4()
        self.assertFalse(action_matches_explicit_request(N8nAction(type="ADD_ITEM",item_id=item_id,quantity=1),"What are you?"))
        self.assertFalse(action_matches_explicit_request(N8nAction(type="ADD_ITEM",item_id=item_id,quantity=1),"Can I add a burger?"))
        self.assertFalse(action_matches_explicit_request(N8nAction(type="REMOVE_ITEM",item_id=item_id),"Show my cart"))
        self.assertFalse(action_matches_explicit_request(N8nAction(type="SET_QUANTITY",item_id=item_id,quantity=2),"Is pizza available?"))
        self.assertTrue(action_matches_explicit_request(N8nAction(type="ADD_ITEM",item_id=item_id,quantity=1),"Add one burger"))
        self.assertTrue(action_matches_explicit_request(N8nAction(type="REMOVE_ITEM",item_id=item_id),"Remove that burger"))
        self.assertTrue(action_matches_explicit_request(N8nAction(type="SET_QUANTITY",item_id=item_id,quantity=2),"Set burger quantity to 2"))

    def test_session_id_is_stable_and_customer_specific(self):
        same_customer=CurrentProfile("customer-1","other@example.com","Other","customer")
        other_customer=CurrentProfile("customer-2","b@example.com","B","customer")
        self.assertEqual(session_id_for(self.profile),session_id_for(same_customer))
        self.assertNotEqual(session_id_for(self.profile),session_id_for(other_customer))

    def test_response_schema_accepts_short_reply(self):
        response=N8nReply.model_validate({"reply":"Hello!","action":None})
        self.assertEqual(response.reply,"Hello!")
        self.assertIsNone(response.action)

    @patch("app.n8n_bridge.Repository.catalogue",new_callable=AsyncMock)
    def test_recommendations_are_generated_from_live_menu_items(self,mock_catalogue):
        item_id=uuid4()
        mock_catalogue.return_value=[{"id":str(item_id),"name":"Zinger Burger","base_price":500,"variants":[],"is_active":True,"is_available":True}]
        reply=asyncio.run(trusted_menu_reply("Suggest something available",[]))
        self.assertIn("Zinger Burger",reply)
        self.assertNotIn("chocolate",reply.lower())

    @patch("app.n8n_bridge.Repository.catalogue",new_callable=AsyncMock)
    def test_recommendations_respect_category_budget_specific_item_and_previous_suggestions(self,mock_catalogue):
        mock_catalogue.return_value=[
            {"id":"burger","name":"Zinger Burger","base_price":500,"variants":[],"is_active":True,"is_available":True,"category":{"name":"Burgers","slug":"burgers"}},
            {"id":"pizza","name":"Chicken Pizza","base_price":900,"variants":[],"is_active":True,"is_available":True,"category":{"name":"Pizza","slug":"pizza"}},
            {"id":"fries","name":"French Fries","base_price":250,"variants":[],"is_active":True,"is_available":True,"category":{"name":"Fries","slug":"fries"}},
        ]
        self.assertIn("Chicken Pizza",asyncio.run(trusted_menu_reply("Suggest a pizza",[])))
        self.assertNotIn("Zinger Burger",asyncio.run(trusted_menu_reply("Suggest a pizza",[])))
        self.assertIn("French Fries",asyncio.run(trusted_menu_reply("Suggest something under Rs 300",[])))
        self.assertIn("Zinger Burger",asyncio.run(trusted_menu_reply("Recommend Zinger Burger",[])))
        history=[HistoryLine(role="assistant",content="Here are verified available options:\n- Zinger Burger — Rs. 500")]
        reply=asyncio.run(trusted_menu_reply("anything else",history))
        self.assertNotIn("Zinger Burger",reply)
        self.assertIn("Chicken Pizza",reply)

    @patch("app.n8n_bridge.Repository.catalogue",new_callable=AsyncMock)
    def test_fictional_and_unavailable_products_are_not_claimed_available(self,mock_catalogue):
        mock_catalogue.return_value=[{"id":"1","name":"Unavailable Burger","is_active":True,"is_available":False}]
        self.assertIn("couldn’t find",asyncio.run(trusted_menu_reply("Do you have cheesecake?",[])))
        self.assertIn("couldn’t find",asyncio.run(trusted_menu_reply("Can you offer Unavailable Burger?",[])))

    @patch("app.n8n_bridge.Repository.catalogue",new_callable=AsyncMock)
    def test_rejected_recommendations_and_spice_followups_do_not_invent_items(self,mock_catalogue):
        mock_catalogue.return_value=[]
        self.assertIn("tell me whether",asyncio.run(trusted_menu_reply("I don't like any of these.",[])))
        self.assertIn("does not record verified spice levels",asyncio.run(trusted_menu_reply("Suggest something mild and not spicy.",[])))

    @patch("app.n8n_bridge.Repository.catalogue",new_callable=AsyncMock)
    def test_menu_lookup_failure_returns_a_friendly_nonfictional_response(self,mock_catalogue):
        mock_catalogue.side_effect=RuntimeError("Supabase unavailable")
        self.assertIn("can’t check",asyncio.run(trusted_menu_reply("Recommend something.",[])))

    @patch("app.n8n_bridge.Repository.catalogue",new_callable=AsyncMock)
    def test_recommendation_conversation_stays_grounded_without_claiming_unrelated_chat(self,mock_catalogue):
        mock_catalogue.return_value=[{"id":"1","name":"Zinger Burger","base_price":500,"variants":[],"is_active":True,"is_available":True}]
        history=[HistoryLine(role="customer",content="Suggest something available"),HistoryLine(role="assistant",content="Here are verified available options: Zinger Burger")]
        self.assertIn("doesn’t currently list",asyncio.run(trusted_menu_reply("I'm craving something sweet",history)))
        self.assertIn("won’t suggest unverified",asyncio.run(trusted_menu_reply("Do you really?",history)))
        self.assertIn("won’t suggest unverified",asyncio.run(trusted_menu_reply("Those aren't on your menu",history)))

    @patch("app.n8n_bridge.Repository.catalogue",new_callable=AsyncMock)
    def test_greetings_identity_questions_and_generic_hunger_go_to_n8n(self,mock_catalogue):
        for customer_message in ("what are you?","hello i am very hungry","hello"):
            with self.subTest(customer_message=customer_message):
                self.assertIsNone(asyncio.run(trusted_menu_reply(customer_message,[])))
        mock_catalogue.assert_not_awaited()

    def test_response_schema_accepts_long_menu_reply(self):
        reply="Pizza menu: "+("Margherita, Pepperoni, Veggie. "*44)
        self.assertGreater(len(reply),1000)
        self.assertLessEqual(len(reply),4000)
        response=N8nReply.model_validate({"reply":reply,"action":None})
        self.assertEqual(response.reply,reply)

    def test_response_schema_preserves_strict_cart_action_validation(self):
        item_id,variant_id=uuid4(),uuid4()
        response=N8nReply.model_validate({
            "reply":"I can add that after your browser confirms it.",
            "action":{"type":"ADD_ITEM","item_id":str(item_id),"variant_id":str(variant_id),"quantity":2},
        })
        self.assertEqual(response.action.type,"ADD_ITEM")
        self.assertEqual(response.action.item_id,item_id)

    def test_currency_normalization_does_not_change_the_price(self):
        self.assertEqual(normalize_currency("Burger: ₱ 450"),"Burger: Rs. 450")
        self.assertEqual(normalize_currency("Pizza: PHP 900"),"Pizza: Rs. 900")

    def test_cheapest_reply_is_compact_and_read_only(self):
        reply=cheapest_reply([{"id":"item-1","name":"Chicken Pizza","category":"Pizza","variant":{"id":"variant-1","name":"Small"},"price":600}])
        self.assertEqual(reply,"The lowest-priced available option is\n- Chicken Pizza (Small) — Rs. 600")

    def test_cart_reply_resolves_prices_from_the_menu_not_the_browser(self):
        item_id,variant_id=uuid4(),uuid4()
        reply=cart_reply([CartLine(item_id=item_id,variant_id=variant_id,quantity=2)],[{
            "id":str(item_id),"name":"Chicken Pizza","base_price":None,
            "variants":[{"id":str(variant_id),"name":"Small 7\"","price":600}],
        }])
        self.assertIn("2 × Chicken Pizza (Small 7\") — Rs. 600 each (Rs. 1200)",reply)
        self.assertIn("Total: Rs. 1200",reply)

    def test_read_only_retry_guard_never_retries_cart_or_mutation_requests(self):
        self.assertTrue(retry_safe(ChatRequest(message="Which burger is cheapest?",message_id=uuid4())))
        self.assertFalse(retry_safe(ChatRequest(message="Add one burger",message_id=uuid4())))
        self.assertFalse(retry_safe(ChatRequest(message="Show the menu",message_id=uuid4(),cart=[CartLine(item_id=uuid4(),quantity=1)])))

    @patch("app.n8n_bridge.Repository.catalogue",new_callable=AsyncMock)
    @patch("app.n8n_bridge.post_to_n8n",new_callable=AsyncMock)
    def test_add_all_four_resolves_exact_verified_items_variants_and_retry_ids(self,mock_post,mock_catalogue):
        ids=[uuid4() for _ in range(4)]; variants=[uuid4() for _ in range(4)]
        names=["Chicken Pizza","Zinger Burger","Chicken Shawarma","French Fries"]
        mock_catalogue.return_value=[{"id":str(item_id),"name":name,"base_price":None,"variants":[{"id":str(variant_id),"name":"Small","price":500,"is_active":True}],"is_active":True,"is_available":True} for item_id,variant_id,name in zip(ids,variants,names)]
        history=[HistoryLine(role="assistant",content="\n".join(f"- {name} (Small) — Rs. 500" for name in names))]
        body=ChatRequest(message="add all four",message_id=self.message_id,history=history)
        first=asyncio.run(message(body,self.profile)); retry=asyncio.run(message(body,self.profile))
        self.assertEqual(first["reply"],"Adding one each of the 4 verified items from the last result.")
        self.assertEqual(len(first["actions"]),4)
        self.assertEqual({action["item_id"] for action in first["actions"]},{str(item_id) for item_id in ids})
        self.assertEqual({action["variant_id"] for action in first["actions"]},{str(variant_id) for variant_id in variants})
        self.assertEqual(first["actions"],retry["actions"])
        mock_post.assert_not_awaited()

    @patch("app.n8n_bridge.Repository.catalogue",new_callable=AsyncMock)
    def test_add_all_four_is_atomic_when_a_prior_result_is_now_unavailable(self,mock_catalogue):
        ids=[uuid4() for _ in range(3)]; names=["Chicken Pizza","Zinger Burger","Chicken Shawarma","French Fries"]
        mock_catalogue.return_value=[{"id":str(item_id),"name":name,"base_price":500,"variants":[],"is_active":True,"is_available":True} for item_id,name in zip(ids,names[:3])]
        history=[HistoryLine(role="assistant",content="\n".join(f"- {name} — Rs. 500" for name in names))]
        response=asyncio.run(message(ChatRequest(message="add all four",message_id=self.message_id,history=history),self.profile))
        self.assertEqual(response["actions"],[])
        self.assertIn("not 4",response["reply"])

    @patch("app.n8n_bridge.Repository.catalogue",new_callable=AsyncMock)
    @patch("app.n8n_bridge.post_to_n8n",new_callable=AsyncMock)
    def test_cart_read_uses_live_prices_without_calling_n8n(self,mock_post,mock_catalogue):
        item_id,variant_id=uuid4(),uuid4()
        mock_catalogue.return_value=[{"id":str(item_id),"name":"Chicken Pizza","base_price":None,"variants":[{"id":str(variant_id),"name":"Small","price":600,"is_active":True}],"is_active":True,"is_available":True}]
        body=ChatRequest(message="show my cart",message_id=self.message_id,cart=[CartLine(item_id=item_id,variant_id=variant_id,quantity=2)])
        response=asyncio.run(message(body,self.profile))
        self.assertIn("Rs. 1200",response["reply"])
        self.assertEqual(response["action"]["type"],"GET_CART")
        mock_post.assert_not_awaited()

    @patch("app.n8n_bridge.post_to_n8n",new_callable=AsyncMock)
    def test_bridge_returns_valid_success_and_stable_action_id(self,mock_post):
        item_id=uuid4(); mock_post.return_value=FakeResponse(payload={"reply":"Added after browser confirmation.","action":{"type":"ADD_ITEM","item_id":str(item_id),"quantity":1}})
        body=ChatRequest(message="Add one burger",message_id=self.message_id)
        response=asyncio.run(message(body,self.profile))
        self.assertEqual(response["reply"],"Added after browser confirmation.")
        self.assertEqual(response["action"]["type"],"ADD_ITEM")
        self.assertEqual(response["action"],action_payload(N8nAction(type="ADD_ITEM",item_id=item_id,quantity=1),self.profile,self.message_id))

    @patch("app.n8n_bridge.post_to_n8n",new_callable=AsyncMock)
    def test_bridge_reports_connection_failure_without_a_second_mutation(self,mock_post):
        mock_post.side_effect=HTTPException(503,"n8n assistant is temporarily unavailable. Please try again shortly.")
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(message(ChatRequest(message="Add one burger",message_id=uuid4()),self.profile))
        self.assertEqual(raised.exception.status_code,503)
        mock_post.assert_awaited_once()

    @patch("app.n8n_bridge.post_to_n8n",new_callable=AsyncMock)
    def test_bridge_rejects_malformed_response(self,mock_post):
        mock_post.return_value=FakeResponse(payload={"reply":"", "action":None})
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(message(ChatRequest(message="Hi",message_id=uuid4()),self.profile))
        self.assertEqual(raised.exception.status_code,502)

    @patch("app.n8n_bridge.post_to_n8n",new_callable=AsyncMock)
    def test_bridge_rejects_unrequested_cart_action(self,mock_post):
        mock_post.return_value=FakeResponse(payload={"reply":"Added.","action":{"type":"ADD_ITEM","item_id":str(uuid4()),"quantity":1}})
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(message(ChatRequest(message="What are you?",message_id=uuid4()),self.profile))
        self.assertEqual(raised.exception.status_code,502)
