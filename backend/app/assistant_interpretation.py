"""Validated language proposals for the draft-only ordering assistant.

Groq may propose one of these values, but it has no cart or database write
capability. The engine validates every identifier, variant and mutation against
the live Supabase menu.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

READ_ONLY={"MENU_QUERY","MENU_FILTER","ITEM_DETAILS","PRICE_QUERY","PRICE_COMPARISON","RECOMMENDATION","VIEW_CART","UNRELATED","CORRECTION_COMPLAINT","SECURITY_MANIPULATION","CANCEL_PENDING_REQUEST"}
MUTATIONS={"ADD_ITEM","REMOVE_ITEM","CHANGE_QUANTITY","CHANGE_VARIANT","CLEAR_CART","UNDO","SET_ORDER_TYPE","SET_ADDRESS"}
VALID_INTENTS=READ_ONLY|MUTATIONS|{"UNKNOWN","GREETING","THANKS"}

@dataclass(frozen=True)
class Interpretation:
    intent: str="UNKNOWN"
    mutation_requested: bool=False
    confidence: float=0.0
    item_ids: tuple[str,...]=field(default_factory=tuple)
    variant_id: str|None=None
    category_slugs: tuple[str,...]=field(default_factory=tuple)
    quantity: int|None=None
    budget: int|None=None
    option_reference: int|None=None
    order_type: str|None=None
    explicit: bool=False

QUESTION=re.compile(r"\b(what|which|show|how much|details|price|cheaper|cheapest|recommend|kitne|konsa|kya|andar|kam)\b|\?",re.I)
COMPLAINT=re.compile(r"\b(did i (say|tell|told)|didn't ask|did not ask|why did you|not what i asked|what are you doing|stupid|nahi mene|mene? (order|add) nahi)\b",re.I)
SECURITY=re.compile(r"\b(ignore.*instruction|admin|api key|system prompt|free food|database|validation|other customer|total.*zero)\b",re.I)
BUDGET=re.compile(r"(?:under|below)\s*(?:rs\.?\s*)?(\d+)|(\d+)\s*(?:ke\s*andar|se\s*kam)",re.I)

def _qty(text:str)->int|None:
    found=re.search(r"\b(\d{1,2}|one|aik|ek|two|three|four|five)\b",text.lower())
    if not found:return None
    return {"one":1,"aik":1,"ek":1,"two":2,"three":3,"four":4,"five":5}.get(found.group(1),int(found.group(1)) if found.group(1).isdigit() else None)

def interpret_fallback(message:str)->Interpretation:
    """Conservative offline fallback: uncertain language never mutates a draft."""
    text=message.strip(); low=text.lower()
    if SECURITY.search(text):return Interpretation("SECURITY_MANIPULATION")
    if COMPLAINT.search(text):return Interpretation("CORRECTION_COMPLAINT")
    if re.search(r"\b(never ?mind|rehne do|ruk jao)\b",low):return Interpretation("CANCEL_PENDING_REQUEST")
    # A question is information unless it contains an explicit cart command.
    # This is deliberately before delivery/pickup recognition so policy or
    # availability questions cannot silently select a fulfilment method.
    if QUESTION.search(text) and not re.search(r"\b(add|remove|clear|cancel|change|make|order|take)\b",low):
        budget=BUDGET.search(low)
        if budget:return Interpretation("MENU_FILTER",False,.95,budget=int(next(x for x in budget.groups() if x)))
        if re.search(r"\b(cheaper|cheapest|sasta|sasti|compare)\b",low):return Interpretation("PRICE_COMPARISON")
        return Interpretation("MENU_QUERY")
    if re.search(r"\b(clear( my)? (cart|order|everything)|cancel everything|remove everything|start (again|over)|new order)\b",low):return Interpretation("CLEAR_CART",True,.9,explicit=True)
    if re.search(r"\b(undo|reverse|previous wala remove|remove previous|cancel previous)\b",low):return Interpretation("UNDO",True,.9,explicit=True)
    if re.search(r"\b(remove|cancel|hata|delete|one less|aik kam|ek kam)\b",low):return Interpretation("REMOVE_ITEM",True,.8,quantity=_qty(text) or 1,explicit=True)
    if re.search(r"\b(make|change|krdo|kar do)\b",low) and re.search(r"\b(small|medium|large|family)\b",low):return Interpretation("CHANGE_VARIANT",True,.8,explicit=True)
    if re.search(r"\b(make|change|krdo|kar do)\b",low) and _qty(text) is not None and not re.search(r"\badd\b",low):return Interpretation("CHANGE_QUANTITY",True,.8,quantity=_qty(text),explicit=True)
    if re.search(r"\b(delivery|deliver|ghar|pickup|takeaway)\b",low):return Interpretation("SET_ORDER_TYPE",True,.8,order_type="pickup" if re.search(r"pickup|takeaway",low) else "delivery",explicit=True)
    if low.startswith("address ") or low.startswith("address:"):return Interpretation("SET_ADDRESS",True,.9,explicit=True)
    budget=BUDGET.search(low)
    if budget:return Interpretation("MENU_FILTER",False,.95,budget=int(next(x for x in budget.groups() if x)))
    if re.search(r"\b(cheaper|cheapest|sasta|sasti|compare)\b",low) and not re.search(r"\b(add|give|take|i.?ll take|order|chahiye|chahye|add kro)\b",low):return Interpretation("PRICE_COMPARISON")
    if re.search(r"\b(add|give|take|i.?ll take|order|chahiye|chahye|add kro|same again|one more|aik aur)\b",low):return Interpretation("ADD_ITEM",True,.75,quantity=_qty(text),explicit=True)
    return Interpretation()

def validate_groq_payload(payload:Any,menu:list[dict])->Interpretation|None:
    """Accept only a narrow, live-menu-grounded Groq structured proposal.

    ``tool_calls`` are deliberately data-only proposals.  They are checked
    against the same current menu before the deterministic engine sees an
    interpretation; they can never invoke a cart/database operation.
    """
    if not isinstance(payload,dict) or payload.get("provider"):return None
    intent=payload.get("intent")
    if intent not in VALID_INTENTS:return None
    ids={str(row["id"]) for row in menu}
    raw_ids=payload.get("item_ids") or ([payload["item_id"]] if payload.get("item_id") else [])
    if not isinstance(raw_ids,list) or any(str(x) not in ids for x in raw_ids):return None
    item_ids=tuple(str(x) for x in raw_ids[:8])
    variant_id=str(payload["variant_id"]) if payload.get("variant_id") else None
    if variant_id and not any(variant_id==str(v["id"]) for row in menu for v in row.get("variants",[])):return None
    categories=tuple(str(x) for x in (payload.get("category_slugs") or ([payload["category"]] if payload.get("category") else []))[:8])
    valid_categories={str(row.get("category_slug")) for row in menu}
    if any(category not in valid_categories for category in categories):return None
    calls=payload.get("tool_calls",[])
    if not isinstance(calls,list) or len(calls)>8:return None
    valid_tools={"search_menu","recommend","compare_products","get_product","get_business_info","propose_cart_action"}
    for call in calls:
        if not isinstance(call,dict) or call.get("name") not in valid_tools:return None
        arguments=call.get("arguments",{})
        if not isinstance(arguments,dict):return None
        proposed_ids=arguments.get("item_ids") or ([arguments["item_id"]] if arguments.get("item_id") else [])
        if not isinstance(proposed_ids,list) or any(str(x) not in ids for x in proposed_ids):return None
        proposed_categories=arguments.get("category_slugs") or ([arguments["category"]] if arguments.get("category") else [])
        if not isinstance(proposed_categories,list) or any(str(x) not in valid_categories for x in proposed_categories):return None
    quantity=payload.get("quantity")
    if quantity is not None and (not isinstance(quantity,int) or not 1<=quantity<=99):return None
    budget=payload.get("budget")
    if budget is not None and (not isinstance(budget,int) or not 0<budget<=100000):return None
    option=payload.get("option_reference")
    if option is not None and (not isinstance(option,int) or not 1<=option<=99):return None
    order_type=payload.get("order_type")
    if order_type not in (None,"delivery","pickup"):return None
    mutation=bool(payload.get("mutation_requested")) and intent in MUTATIONS
    return Interpretation(intent,mutation,float(payload.get("confidence",0) or 0),item_ids,variant_id,categories,quantity,budget,option,order_type,mutation)

# Kept as a private compatibility alias for deployments that imported the old
# helper directly.  Application code uses validate_groq_payload.
validate_gemini_payload=validate_groq_payload
