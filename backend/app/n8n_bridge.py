"""Authenticated, schema-validated bridge from the customer browser to n8n."""
import asyncio
import json
import logging
import os
import re
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .auth import CurrentProfile, require_roles
from .assistant import Repository, cheapest_available_offers, matches_menu_category

router=APIRouter(prefix="/assistant/n8n",tags=["assistant-n8n"])
logger=logging.getLogger(__name__)

class CartLine(BaseModel):
    model_config=ConfigDict(extra="forbid")
    item_id:UUID; variant_id:UUID|None=None; quantity:int=Field(ge=1,le=99)

class HistoryLine(BaseModel):
    model_config=ConfigDict(extra="forbid")
    role:Literal["customer","assistant"]; content:str=Field(min_length=1,max_length=500)

class ChatRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    message:str=Field(min_length=1,max_length=2000); message_id:UUID
    cart:list[CartLine]=Field(default_factory=list,max_length=50)
    history:list[HistoryLine]=Field(default_factory=list,max_length=8)

class N8nAction(BaseModel):
    model_config=ConfigDict(extra="forbid")
    type:Literal["ADD_ITEM","REMOVE_ITEM","SET_QUANTITY","GET_CART"]
    item_id:UUID|None=None; variant_id:UUID|None=None; quantity:int|None=None

    def model_post_init(self, __context):
        if self.type=="GET_CART":
            if self.item_id is not None or self.variant_id is not None or self.quantity is not None: raise ValueError("GET_CART has no item fields")
        elif self.item_id is None: raise ValueError("item_id is required")
        elif self.type=="ADD_ITEM" and (self.quantity is None or not 1<=self.quantity<=99): raise ValueError("ADD_ITEM quantity must be 1-99")
        elif self.type=="REMOVE_ITEM" and self.quantity is not None and not 1<=self.quantity<=99: raise ValueError("REMOVE_ITEM quantity must be 1-99")
        elif self.type=="SET_QUANTITY" and (self.quantity is None or not 0<=self.quantity<=99): raise ValueError("SET_QUANTITY quantity must be 0-99")

class N8nReply(BaseModel):
    model_config=ConfigDict(extra="forbid")
    # Complete category/menu answers may be longer than conversational replies.
    # Keep a finite cap so upstream responses remain bounded.
    reply:str=Field(min_length=1,max_length=4000); action:N8nAction|None=None
    actions:list[N8nAction]=Field(default_factory=list,max_length=25)

def settings()->tuple[str,str]:
    url=os.getenv("N8N_CHAT_WEBHOOK_URL","").strip(); secret=os.getenv("N8N_WEBHOOK_SECRET","")
    if not url or not secret: raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,"n8n assistant is not configured")
    return url,secret

def action_payload(action:N8nAction|None,profile:CurrentProfile,message_id:UUID)->dict|None:
    if not action:return None
    body=action.model_dump(mode="json",exclude_none=True)
    stable=uuid5(NAMESPACE_URL,f"pizza-point:{profile.id}:{message_id}:{json.dumps(body,sort_keys=True)}")
    return {"action_id":str(stable),**body}

def action_payloads(actions:list[N8nAction],profile:CurrentProfile,message_id:UUID)->list[dict]:
    return [payload for action in actions if (payload:=action_payload(action,profile,message_id))]

def session_id_for(profile:CurrentProfile)->str:
    """Stable n8n conversation key derived only from verified customer identity."""
    return str(uuid5(NAMESPACE_URL,f"pizza-point:n8n-session:{profile.id}"))

CHEAPEST_REQUEST=re.compile(r"\b(cheapest|lowest(?:[- ]priced)?|least expensive|sasta)\b",re.I)
CART_READ_REQUEST=re.compile(r"\b(?:what(?:'s| is) in (?:my )?cart|show (?:me )?(?:my )?cart|(?:my )?cart (?:contents|details|summary)|cart dikhao)\b",re.I)
MUTATION_WORDS=re.compile(r"\b(?:add|remove|delete|update|set|make|change|order|checkout|buy|cart)\b",re.I)
RECOMMENDATION_REQUEST=re.compile(r"\b(?:recommend|suggest|what should i|get me something|i don't like any|i do not like any)\b",re.I)
AVAILABILITY_REQUEST=re.compile(r"\b(?:do you have|can you offer|offer me)\b",re.I)
SPICE_REQUEST=re.compile(r"\b(?:mild|spicy|spice)\b",re.I)
APPETITE_REQUEST=re.compile(r"\b(?:craving|sweet|dessert|salad|milkshake|brownie|churro|cake)\b",re.I)
MENU_CHALLENGE=re.compile(r"\b(?:do you really|really\?|those aren'?t|not on (?:your |the )?menu|you (?:made|invented|suggested) that)\b",re.I)
EXPLICIT_MENU_CHALLENGE=re.compile(r"\b(?:those aren'?t|not on (?:your |the )?menu|you (?:made|invented|suggested) that)\b",re.I)
REJECTION_REQUEST=re.compile(r"\b(?:i (?:do not|don't) want (?:this|that|it|any)|anything else|something else|not this|not that|no thanks|another option)\b",re.I)
BUDGET_REQUEST=re.compile(r"\b(?:under|below|less than|upto|up to)\s*(?:rs\.?\s*)?(\d{1,6})\b",re.I)
ADD_ACTION_REQUEST=re.compile(r"\b(?:add|order|buy|put)\b",re.I)
REMOVE_ACTION_REQUEST=re.compile(r"\b(?:remove|delete|take (?:out|off)|cancel)\b",re.I)
QUANTITY_ACTION_REQUEST=re.compile(r"\b(?:set|change|increase|decrease|make|update)\b",re.I)
MULTI_ADD_REQUEST=re.compile(r"\b(?:add|order|put)\s+(?:all\s+)?(one|two|three|four|five|six|seven|eight|nine|\d{1,2})\b",re.I)
NUMBER_WORDS={"one":1,"two":2,"three":3,"four":4,"five":5,"six":6,"seven":7,"eight":8,"nine":9}

def normalize_currency(reply:str)->str:
    """Correct an upstream currency glyph without changing prices or menu data."""
    return re.sub(r"(?:Rs.\s*|\bPHP\s*)","Rs. ",reply,flags=re.I)

def cheapest_reply(offers:list[dict])->str:
    if not offers:
        return "There are no available menu items to compare right now."
    lines=[]
    for offer in offers:
        label=offer["name"]+(f" ({offer['variant']['name']})" if offer["variant"] else "")
        lines.append(f"{label} — Rs. {offer['price']}")
    prefix="The lowest-priced available option is" if len(lines)==1 else "The lowest-priced available options are"
    return prefix+"\n"+"\n".join(f"- {line}" for line in lines)

async def cheapest_fallback(customer_message:str)->str|None:
    """Read-only resilience for a known workflow failure; never mutates a cart."""
    if not CHEAPEST_REQUEST.search(customer_message):
        return None
    items=await Repository().catalogue()
    matching_categories=[item for item in items if matches_menu_category(item,customer_message)]
    return cheapest_reply(cheapest_available_offers(matching_categories or items))

def money_text(value:object)->str:
    amount=float(value)
    return str(int(amount)) if amount.is_integer() else f"{amount:.2f}".rstrip("0").rstrip(".")

def cart_reply(cart:list[CartLine],items:list[dict])->str:
    """Render the authenticated request's browser cart using server menu prices."""
    if not cart:
        return "Your cart is currently empty."
    by_id={str(item["id"]):item for item in items}
    lines=[]; total=0.0; unverified=0
    for line in cart:
        item=by_id.get(str(line.item_id))
        if not item:
            unverified+=1; continue
        variant=None
        if line.variant_id is not None:
            variant=next((candidate for candidate in item.get("variants",[]) if str(candidate.get("id"))==str(line.variant_id)),None)
            if not variant:
                unverified+=1; continue
            price=variant.get("price"); label=f"{item['name']} ({variant['name']})"
        else:
            price=item.get("base_price"); label=item["name"]
        if price is None:
            unverified+=1; continue
        subtotal=float(price)*line.quantity; total+=subtotal
        lines.append(f"- {line.quantity} × {label} — Rs. {money_text(price)} each (Rs. {money_text(subtotal)})")
    if not lines:
        return "I couldn't verify the items in this cart against the current menu."
    reply="Your cart:\n"+"\n".join(lines)+f"\n\nTotal: Rs. {money_text(total)}"
    return reply+("\n\nOne cart line could not be verified against the current menu." if unverified==1 else f"\n\n{unverified} cart lines could not be verified against the current menu." if unverified else "")

async def cart_read_fallback(body:ChatRequest)->str|None:
    if not CART_READ_REQUEST.search(body.message):
        return None
    return cart_reply(body.cart,await Repository().catalogue())

def menu_price(item:dict)->str:
    prices=[variant.get("price") for variant in item.get("variants",[]) if variant.get("is_active") and variant.get("price") is not None]
    value=item.get("base_price") if item.get("base_price") is not None else (min(prices) if prices else None)
    return money_text(value) if value is not None else "price on request"

def menu_item_price(item:dict)->float|None:
    """Return the only price we can safely use when filtering recommendations."""
    prices=[variant.get("price") for variant in item.get("variants",[]) if variant.get("is_active") and variant.get("price") is not None]
    value=item.get("base_price") if item.get("base_price") is not None else (min(prices) if prices else None)
    return float(value) if value is not None else None

def suggested_item_ids(items:list[dict],history:list[HistoryLine])->set[str]:
    """Infer prior suggestions only from verified menu names present in assistant replies."""
    assistant_text=" ".join(entry.content.lower() for entry in history if entry.role=="assistant")
    return {str(item["id"]) for item in items if item["name"].lower() in assistant_text}

def recommendation_candidates(items:list[dict],message:str,history:list[HistoryLine])->list[dict]:
    """Filter live items by the customer's stated category/budget and recent suggestions."""
    candidates=[item for item in items if menu_item_price(item) is not None]
    category_matches=[item for item in candidates if matches_menu_category(item,message)]
    if category_matches:
        candidates=category_matches
    budget=BUDGET_REQUEST.search(message)
    if budget:
        limit=float(budget.group(1)); candidates=[item for item in candidates if menu_item_price(item) is not None and menu_item_price(item)<=limit]
    mentioned=[item for item in candidates if item["name"].lower() in message.lower()]
    if mentioned:
        candidates=mentioned
    elif history:
        previous=suggested_item_ids(items,history)
        alternatives=[item for item in candidates if str(item["id"]) not in previous]
        if alternatives or REJECTION_REQUEST.search(message):
            candidates=alternatives
    return candidates

def action_matches_explicit_request(
    action: N8nAction, message: str, history: list[HistoryLine] | None = None
) -> bool:
    """Reject cart mutations unless the customer's message explicitly requests them.

    A short item name is accepted as a clarification only after the assistant asked
    which item to remove.
    """
    history = history or []
    text = message.strip()
    if (
        RECOMMENDATION_REQUEST.search(text)
        or re.search(r"\b(?:can|could|should) i\b|\bhow (?:do|can) i\b", text, re.I)
        or text.endswith("?")
    ):
        return action.type == "GET_CART" and bool(CART_READ_REQUEST.search(text))
    if action.type == "GET_CART":
        return bool(CART_READ_REQUEST.search(text))
    if action.type == "ADD_ITEM":
        return bool(ADD_ACTION_REQUEST.search(text))
    if action.type == "REMOVE_ITEM":
        if REMOVE_ACTION_REQUEST.search(text):
            return True
        recent = history[-4:]
        pending_removal = any(
            entry.role == "assistant" and re.search(
                r"\bwhich\b.*\b(?:remove|pizza|item|burger)\b|\b(?:which|what)\s+(?:pizza|item|burger)\b",
                entry.content, re.I
            ) for entry in recent
        )
        return pending_removal and bool(text) and len(text) <= 100
    return bool(
        QUANTITY_ACTION_REQUEST.search(text)
        or re.search(r"\b(?:to|down to|up to)\s+(?:zero|one|two|three|four|five|six|seven|eight|nine|\d{1,2})\b", text, re.I)
    )

def multi_add_count(message:str)->int|None:
    match=MULTI_ADD_REQUEST.search(message)
    if not match:return None
    value=match.group(1).lower()
    return NUMBER_WORDS.get(value,int(value) if value.isdigit() else 0)

def last_verified_results(items:list[dict],history:list[HistoryLine])->tuple[list[dict],str]:
    """Extract exact current-menu names from the latest assistant result only."""
    for entry in reversed(history):
        if entry.role!="assistant":continue
        text=entry.content.lower()
        matches=[item for item in items if item["name"].lower() in text]
        if matches:
            matches.sort(key=lambda item:text.find(item["name"].lower()))
            return matches,entry.content
    return [],""

def selected_variant(item:dict,result_text:str)->dict|None:
    variants=[variant for variant in item.get("variants",[]) if variant.get("is_active") and variant.get("price") is not None]
    if not variants:return None
    named=[variant for variant in variants if variant["name"].lower() in result_text.lower()]
    return named[0] if len(named)==1 else (variants[0] if len(variants)==1 else None)

async def resolve_multi_add(body: ChatRequest) -> tuple[str, list[N8nAction]] | None:
    """Resolve explicit quantities only against active, available catalogue items.

    The requested quantity (for example, 2 burgers) is not the number of menu
    results. Named items are resolved directly; ambiguous category requests ask
    the customer to choose instead of adding arbitrary items.
    """
    count = multi_add_count(body.message)
    if count is None or count < 2:
        return None
    try:
        items = [
            item for item in await Repository().catalogue()
            if item.get("is_active") and item.get("is_available")
        ]
    except Exception as exc:
        logger.warning("multi_add_lookup_failed error=%s", type(exc).__name__)
        return ("I can't verify the available menu right now, so I have not changed your cart.", [])

    message_text = re.sub(r"[^a-z0-9 ]+", " ", body.message.lower())
    # Prefer exact menu names explicitly mentioned by the customer.
    named = [item for item in items if re.sub(r"[^a-z0-9 ]+", " ", item["name"].lower()).strip() in message_text]
    if len(named) == 1:
        item = named[0]
        variant = selected_variant(item, body.message)
        if item.get("variants") and variant is None:
            return (f"Which size would you like for {item['name']}? I haven't changed your cart.", [])
        if not item.get("variants") and item.get("base_price") is None:
            return (f"I can't verify the price for {item['name']}, so I have not changed your cart.", [])
        action = N8nAction(type="ADD_ITEM", item_id=item["id"], variant_id=variant["id"] if variant else None, quantity=count)
        return (f"Adding {count} of {item['name']} to your cart.", [action])

    # If the customer refers to a category (e.g. "2 burgers"), do not guess.
    category_matches = [item for item in items if matches_menu_category(item, body.message)]
    if len(category_matches) == 1:
        item = category_matches[0]
        variant = selected_variant(item, body.message)
        if item.get("variants") and variant is None:
            return (f"Which size would you like for {item['name']}? I haven't changed your cart.", [])
        if not item.get("variants") and item.get("base_price") is None:
            return (f"I can't verify the price for {item['name']}, so I have not changed your cart.", [])
        return (f"Adding {count} of {item['name']} to your cart.", [N8nAction(type="ADD_ITEM", item_id=item["id"], variant_id=variant["id"] if variant else None, quantity=count)])
    if len(category_matches) > 1:
        names = ", ".join(item["name"] for item in category_matches[:5])
        return (f"I found several available matches: {names}. Which one would you like to add?", [])

    # Support "add 2" after the assistant displayed a verified menu list.
    results, result_text = last_verified_results(items, body.history)
    if len(results) == 1:
        item = results[0]
        variant = selected_variant(item, result_text)
        if item.get("variants") and variant is None:
            return (f"I can't verify the selected size for {item['name']}, so I have not changed your cart.", [])
        if not item.get("variants") and item.get("base_price") is None:
            return (f"I can't verify the price for {item['name']}, so I have not changed your cart.", [])
        return (f"Adding {count} of {item['name']} to your cart.", [N8nAction(type="ADD_ITEM", item_id=item["id"], variant_id=variant["id"] if variant else None, quantity=count)])
    if len(results) > 1:
        return ("Which of the recently shown items would you like to add, and in what size if applicable?", [])
    return ("I couldn't verify which available menu item you mean. Please tell me its exact menu name; I haven't changed your cart.", [])

def has_menu_context(history:list[HistoryLine])->bool:
    """Recognise short follow-ups after a menu conversation without trusting AI text."""
    recent=" ".join(entry.content.lower() for entry in history[-4:])
    return bool(RECOMMENDATION_REQUEST.search(recent) or AVAILABILITY_REQUEST.search(recent) or "pizza point's current menu" in recent or "verified available" in recent)

async def trusted_menu_reply(customer_message:str,history:list[HistoryLine])->str|None:
    """Answer recommendation claims from live Supabase data, never model text."""
    if MUTATION_WORDS.search(customer_message): return None
    contextual_followup=has_menu_context(history) and (len(customer_message.split())<=8 or MENU_CHALLENGE.search(customer_message))
    relevant_request=bool(RECOMMENDATION_REQUEST.search(customer_message) or AVAILABILITY_REQUEST.search(customer_message) or SPICE_REQUEST.search(customer_message) or APPETITE_REQUEST.search(customer_message) or EXPLICIT_MENU_CHALLENGE.search(customer_message) or (REJECTION_REQUEST.search(customer_message) and has_menu_context(history)) or contextual_followup)
    if not relevant_request: return None
    try: items=[item for item in await Repository().catalogue() if item.get("is_active") and item.get("is_available")]
    except Exception as exc:
        logger.warning("trusted_menu_lookup_failed error=%s",type(exc).__name__)
        return "I can't check Pizza Point's current menu right now. Please try again shortly."
    if SPICE_REQUEST.search(customer_message): return "Pizza Point's current menu does not record verified spice levels, so I can't safely recommend a mild item."
    if MENU_CHALLENGE.search(customer_message): return "You're right to check. I can only confirm products listed as active and available on Pizza Point's current menu, and I won't suggest unverified items."
    normalized=re.sub(r"[^a-z0-9 ]+"," ",customer_message.lower())
    matches=[item for item in items if item["name"].lower() in normalized]
    if AVAILABILITY_REQUEST.search(customer_message):
        if not matches: return "I couldn't find that item on Pizza Point's current menu."
        item=matches[0]; return f"Yes — {item['name']} is currently available from Rs. {menu_price(item)}."
    if "don't like any" in customer_message.lower() or "do not like any" in customer_message.lower():
        return "I can suggest verified menu items if you tell me whether you prefer pizza, burgers, shawarma, pasta,fries, or drinks."
    if APPETITE_REQUEST.search(customer_message) and any(word in customer_message.lower() for word in ("sweet","dessert","salad","milkshake","brownie","churro","cake")):
        return "Pizza Point doesn't currently list a verified available item in that category. I can help with a pizza, burger, shawarma, pasta, fries, or drink instead."
    choices=recommendation_candidates(items,customer_message,history)
    if not choices:
        if REJECTION_REQUEST.search(customer_message):
            return "No unshown verified option matches that yet. Would you prefer pizza, burgers, shawarma, pasta, fries, or drinks?"
        return "I couldn't find a verified available menu item matching that request."
    choices=choices[:3]
    return "Here are verified available options:\n"+"\n".join(f"- {item['name']} — Rs. {menu_price(item)}" for item in choices)

def retry_safe(body:ChatRequest)->bool:
    """Only retry requests that cannot create, alter, or confirm a cart action."""
    return not body.cart and not MUTATION_WORDS.search(body.message)

async def post_to_n8n(url:str,secret:str,payload:dict,*,allow_retry:bool)->httpx.Response:
    """Retry only transient transport/gateway failures for read-only requests."""
    attempts=2 if allow_retry else 1
    last_error:Exception|None=None
    async with httpx.AsyncClient(timeout=15,trust_env=False) as client:
        for attempt in range(attempts):
            try:
                response=await client.post(url,json=payload,headers={"X-Pizza-Point-Webhook-Secret":secret})
            except (httpx.ConnectError,httpx.ConnectTimeout,httpx.ReadTimeout,httpx.RemoteProtocolError) as exc:
                last_error=exc
                logger.warning("n8n_transport_failure attempt=%s retry_safe=%s error=%s",attempt+1,allow_retry,type(exc).__name__)
                if attempt+1<attempts:
                    await asyncio.sleep(.25)
                    continue
                raise HTTPException(503,"n8n assistant is temporarily unavailable. Please try again shortly.") from exc
            if response.status_code in {502,503,504} and attempt+1<attempts:
                logger.warning("n8n_gateway_failure attempt=%s status=%s",attempt+1,response.status_code)
                await asyncio.sleep(.25)
                continue
            return response
    raise HTTPException(503,"n8n assistant is temporarily unavailable. Please try again shortly.") from last_error

@router.post("/messages")
async def message(body:ChatRequest,profile:CurrentProfile=Depends(require_roles("customer"))):
    trusted_reply=await trusted_menu_reply(body.message,body.history)
    if trusted_reply is not None: return {"reply":trusted_reply,"action":None}
    multi_add=await resolve_multi_add(body)
    if multi_add is not None:
        reply,actions=multi_add
        return {"reply":reply,"action":None,"actions":action_payloads(actions,profile,body.message_id)}
    cart_fallback=await cart_read_fallback(body)
    if cart_fallback is not None:
        return {"reply":cart_fallback,"action":action_payload(N8nAction(type="GET_CART"),profile,body.message_id)}
    url,secret=settings()
    payload={"customer_id":profile.id,"session_id":session_id_for(profile),"message":body.message,"message_id":str(body.message_id),"cart":[x.model_dump(mode="json",exclude_none=True) for x in body.cart],"history":[x.model_dump() for x in body.history]}
    try:
        response=await post_to_n8n(url,secret,payload,allow_retry=retry_safe(body))
    except HTTPException:
        raise
    except httpx.HTTPError as exc:
        logger.warning("n8n_transport_failure retry_safe=%s error=%s",retry_safe(body),type(exc).__name__)
        raise HTTPException(503,"n8n assistant is temporarily unavailable. Please try again shortly.") from exc
    if response.status_code>=400:
        logger.warning("n8n_upstream_failure status=%s retry_safe=%s",response.status_code,retry_safe(body))
        fallback=await cheapest_fallback(body.message)
        if fallback is not None:
            return {"reply":fallback,"action":None}
        raise HTTPException(502,"The assistant could not complete that request, and your cart was not changed. Please try again.")
    try: result=N8nReply.model_validate(response.json())
    except (ValidationError,ValueError,json.JSONDecodeError) as exc:
        logger.warning("n8n_invalid_response content_type=%s error=%s",response.headers.get("content-type",""),type(exc).__name__)
        raise HTTPException(502,"n8n assistant returned an invalid response. Please try again.") from exc
    returned_actions=([result.action] if result.action else [])+result.actions
    if any(not action_matches_explicit_request(action, body.message, body.history) for action in returned_actions):
        logger.warning("n8n_unrequested_action")
        raise HTTPException(502,"The assistant could not safely verify that cart change. Please state the item and change you want.")
    return {"reply":normalize_currency(result.reply),"action":action_payload(result.action,profile,body.message_id),"actions":action_payloads(result.actions,profile,body.message_id)}
