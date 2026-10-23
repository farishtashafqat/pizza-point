"""Phase 6A: grounded, draft-only Pizza Point assistant.



The language layer may suggest an intent, but this module is the only place that

matches menu rows and mutates persisted draft state.  It never creates orders.

"""

import json

import logging

import os

import re

from dataclasses import dataclass, field

from difflib import SequenceMatcher

from typing import Any



import httpx

from fastapi import APIRouter, Depends, HTTPException, Query

from pydantic import BaseModel, Field



from .auth import CurrentProfile, require_assistant_menu_key, require_roles, service_settings

from .assistant_interpretation import VALID_INTENTS, Interpretation, interpret_fallback, validate_groq_payload



router = APIRouter(prefix="/assistant", tags=["assistant"])

logger=logging.getLogger("pizza_point.assistant")



INJECTION = re.compile(r"(ignore .*?(instruction|rule|validation)|system prompt|api key|service.?role|act as admin|other customer|change (the )?(database|price)|total (to )?zero|free (food|deal)|pretend .*cost|admin.?only)", re.I)

RESET = re.compile(r"\b(clear( my)? (cart|order|everything)|cancel everything|remove everything|start (again|over)|new order)\b", re.I)

CANCEL_PENDING = re.compile(r"\b(never ?mind|rehne do|cancel|ruk jao)\b", re.I)

UNDO = re.compile(r"\b(undo|reverse|previous wala remove|remove previous|cancel previous|take the last thing out)\b", re.I)

ORDER_TYPE = {"delivery": re.compile(r"\b(delivery|deliver|ghar)\b", re.I), "pickup": re.compile(r"\b(pick ?up|takeaway)\b", re.I)}

CATEGORY_WORDS = {"pizza": ["pizza", "pizzas", "piza", "pizz"], "burgers": ["burger", "burgers", "burgur"], "shawarma": ["shawarma", "shawarmas", "shawrma"], "paratha-rolls": ["paratha", "paratas", "parata", "roll"], "fries-sides": ["fries", "fraiz", "loaded fries"], "pasta": ["pasta", "pastas"], "deals": ["deal", "deals"]}

ADD_WORDS = re.compile(r"\b(add|give|want|need|chahiye|chahye|kro|kar do|order|another|aur)\b", re.I)

REMOVE_WORDS = re.compile(r"\b(remove|cancel|hata|delete|kam)\b", re.I)

QUESTION_WORDS = re.compile(r"\b(price|kitne|kya hai|what|show|available|have|cheapest|expensive|compare|sizes?)\b|\?", re.I)

def norm(value: str) -> str:

    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()



def qty_from(text: str, default: int = 1) -> int:

    m = re.search(r"\b(\d{1,2}|one|aik|ek|two|three|four|five)\b", text.lower())

    if not m: return default

    return {"one":1,"aik":1,"ek":1,"two":2,"three":3,"four":4,"five":5}.get(m.group(1), int(m.group(1)) if m.group(1).isdigit() else default)



ORDINALS={"first":1,"1st":1,"one":1,"second":2,"2nd":2,"third":3,"3rd":3,"fourth":4,"4th":4,"fifth":5,"5th":5,"sixth":6,"6th":6,"seventh":7,"7th":7}



def money(value: Any) -> float: return round(float(value or 0), 2)



@dataclass

class DraftLine:

    item_id: str; variant_id: str | None; quantity: int



@dataclass

class AssistantState:

    pending: dict | None = None

    context: dict = field(default_factory=dict)

    order_type: str | None = None

    delivery_address: str | None = None

    lines: list[DraftLine] = field(default_factory=list)



class Engine:

    """Deterministic executor. `menu` contains only current active/available rows."""

    def __init__(self, menu: list[dict]):

        self.menu = menu

        self._interpretation = Interpretation()

        self._raw = ""



    def begin(self, raw: str, interpretation: Interpretation | None) -> None:

        self._raw = raw

        self._interpretation = interpretation or interpret_fallback(raw)



    def allowed(self, action: str, state: AssistantState, *, pending_selection: bool = False) -> bool:

        """The single backend mutation gate. A model proposal is never enough."""

        intent = self._interpretation.intent

        if intent in {"SECURITY_MANIPULATION", "CORRECTION_COMPLAINT"}:

            return False

        low = norm(self._raw)

        verbs = {

            "ADD_ITEM": r"\b(add|give|take|i ll take|order|chahiye|chahye|add kro|same again|one more|aik aur)\b",

            "REMOVE_ITEM": r"\b(remove|cancel|hata|delete|one less|aik kam|ek kam)\b",

            "CLEAR_CART": r"\b(clear|cancel everything|remove everything|start again|start over|new order)\b",

            "CHANGE_QUANTITY": r"\b(make|change|krdo|kar do)\b",

            "CHANGE_VARIANT": r"\b(make|change|krdo|kar do|instead|wala)\b",

            "UNDO": r"\b(undo|reverse|previous wala remove|remove previous|cancel previous)\b",

            "SET_ORDER_TYPE": r"\b(delivery|deliver|ghar|pickup|takeaway)\b",

            "SET_ADDRESS": r"\baddress\b",

        }

        if pending_selection and action == "ADD_ITEM":

            return bool(re.fullmatch(r"\s*(?:\d+|first|second|third|fourth|fifth|sixth|seventh|last|cheapest one|sasta(?:\s+wala)?|(?:rs\s*)?\d{2,5}(?:\s+wala)?|small|medium|large|family)(?:\s+one)?\s*", low))

        return intent == action and self._interpretation.mutation_requested and bool(re.search(verbs.get(action, r"$^"), low, re.I))



    def categories(self, text: str) -> list[dict]:

        slugs = [slug for slug, terms in CATEGORY_WORDS.items() if any(term in norm(text) for term in terms)]

        return [x for x in self.menu if x.get("category_slug") in slugs] if slugs else []



    def category_slugs(self, text: str, interpretation: Interpretation) -> list[str]:

        if interpretation.category_slugs:

            return list(interpretation.category_slugs)

        message=norm(text)

        found=[]

        for slug,terms in CATEGORY_WORDS.items():

            positions=[message.find(term) for term in terms if message.find(term)>=0]

            if positions: found.append((min(positions),slug))

        return [slug for _,slug in sorted(found)]



    def match(self, text: str, candidates: list[dict] | None = None) -> list[dict]:

        hay = norm(text); source = candidates or self.menu

        exact = [x for x in source if norm(x["name"]) in hay or hay in norm(x["name"])]

        if exact: return exact

        words=hay.split()

        scores=[]

        for item in source:

            item_words=norm(item["name"]).split()

            # A recognisable name token ("zingr", "piza") is safer than comparing

            # an entire conversational sentence with an item name.

            score=max((SequenceMatcher(None,w,iw).ratio() for w in words for iw in item_words),default=0)

            scores.append((score,item))

        scores.sort(reverse=True,key=lambda x:x[0])

        if not scores or scores[0][0]<.76:return []

        top=scores[0][0]

        return [item for score,item in scores if score>=max(.76,top-.035)][:2]



    def exact_mentions(self, text: str) -> list[dict]:

        """Products explicitly named in a message, in menu order.



        This is the only multi-product source used by cart actions. Similarity

        may help offer a clarification, but cannot turn one mention into many

        additions.

        """

        hay=norm(text)

        return [item for item in self.menu if norm(item["name"]) in hay]



    def action_mentions(self, text: str) -> list[dict]:

        """Resolve independently-delimited action entities without fan-out."""

        exact=self.exact_mentions(text)

        if exact:return exact

        resolved=[]

        for part in re.split(r"\b(?:and|aur)\b",norm(text)):

            candidates=self.match(part)

            if not candidates:continue

            # If a base product is the unmodified subset of a longer match,

            # select it; otherwise retain ambiguity for clarification.

            base=next((x for x in candidates if all(set(norm(x["name"]).split()).issubset(set(norm(y["name"]).split())) for y in candidates)),None)

            if base and base not in resolved:resolved.append(base)

        return resolved



    def unavailable_specific_request(self, text: str, slugs: list[str]) -> bool:

        """Detect a product-shaped question that has no live product match."""

        if not slugs or not QUESTION_WORDS.search(text): return False

        words=set(norm(text).split())

        ignored={"do","you","have","is","it","available","what","which","show","price","kitne","kya","hai","ka","ki","ke","the","a","an","and","aur","cheapest","cheaper","sasta","compare","menu","instead","please"}

        for terms in CATEGORY_WORDS.values(): ignored.update(terms)

        meaningful=words-ignored

        if not meaningful:return False

        scoped=[item for item in self.menu if item.get("category_slug") in slugs]

        return not any(meaningful.issubset(set(norm(item["name"]).split())) for item in scoped)



    def variant(self, item: dict, text: str) -> dict | None:

        variants = item.get("variants", [])

        if not variants: return None

        n = norm(text)

        for variant in variants:

            if norm(variant["name"]) in n or n in norm(variant["name"]): return variant

        best = sorted(((SequenceMatcher(None,n,norm(v["name"])).ratio(),v) for v in variants), reverse=True, key=lambda x:x[0])

        return best[0][1] if best and best[0][0] >= .72 else None



    def render_options(self, items: list[dict]) -> str:

        return "\n".join(f"{i+1}. {x['name']} — Rs. {self.price(x):.0f}" for i,x in enumerate(items))



    def render_categories(self, slugs: list[str]) -> str:

        sections=[]

        for slug in slugs:

            items=[x for x in self.menu if x.get("category_slug")==slug]

            if items:

                sections.append(f"{items[0].get('category_name') or slug.title()}\n"+self.render_options(items))

        return "\n\n".join(sections)



    def price(self, item: dict, variant: dict | None = None) -> float:

        return money(variant["price"] if variant else item.get("base_price") or (item.get("variants") or [{}])[0].get("price"))



    def draft(self, state: AssistantState) -> dict:

        lines=[]; total=0.0

        for line in state.lines:

            item=next((x for x in self.menu if x["id"]==line.item_id),None)

            if not item: continue

            variant=next((v for v in item.get("variants",[]) if v["id"]==line.variant_id),None)

            unit=self.price(item,variant); subtotal=round(unit*line.quantity,2); total+=subtotal

            lines.append({"item_id":item["id"],"name":item["name"],"category":item.get("category_name"),"variant_id":line.variant_id,"variant":variant and variant["name"],"quantity":line.quantity,"unit_price":unit,"subtotal":subtotal})

        return {"items":lines,"total":round(total,2),"count":sum(x["quantity"] for x in lines)}



    def add(self,state:AssistantState,item:dict,variant:dict|None,quantity:int,*,pending_selection:bool=False)->str:

        if not self.allowed("ADD_ITEM",state,pending_selection=pending_selection): return "I can show details and prices, but please clearly ask me to add an item before I change your draft cart."

        quantity=max(1,min(99,quantity)); vid=variant and variant["id"]

        line=next((x for x in state.lines if x.item_id==item["id"] and x.variant_id==vid),None)

        if line: line.quantity=min(99,line.quantity+quantity)

        else: state.lines.append(DraftLine(item["id"],vid,quantity))

        label=f"{quantity} × {item['name']}"+(f" ({variant['name']})" if variant else "")

        state.context["last_item_id"]=item["id"]; state.context["last_variant_id"]=vid

        return f"Added {label}."



    def remove(self,state:AssistantState,target:str,quantity:int|None=None,all_category:bool=False)->str:

        if not self.allowed("REMOVE_ITEM",state): return "Please clearly ask me to remove an item before I change your draft cart."

        candidates=self.categories(target) if all_category else self.match(target)

        ids={x["id"] for x in candidates}

        affected=[x for x in state.lines if x.item_id in ids]

        if not affected: return "That item is not in your draft cart."

        if all_category:

            state.lines=[x for x in state.lines if x.item_id not in ids]; return "Removed those items from your draft cart."

        if len(affected)>1 and not quantity: return "Which one should I remove? Please name the size or item."

        line=affected[0]; amount=quantity or line.quantity

        if amount>=line.quantity: state.lines.remove(line)

        else: line.quantity-=amount

        return "Updated your draft cart."



    def resolve_pending(self,state:AssistantState,text:str)->str|None:

        pending=state.pending

        if not pending:return None

        if CANCEL_PENDING.search(text): state.pending=None; return "No problem — I cancelled that selection. Your existing draft cart is unchanged."

        choices=[x for x in self.menu if x["id"] in pending.get("item_ids",[])]

        low=norm(text)

        if re.search(r"\b(any other|koi (aur|or)|kuch aur|aur kya|or dikhao|aur dikhao|something else)\b",low):

            return "Those are the currently available options here. I can also show pizzas, shawarma, fries, pasta, or deals."

        if re.search(r"\b(cheapest|sasta|cheaper)\b",low) and choices:

            choice=min(choices,key=self.price)

            if pending["kind"]=="item":

                state.pending=None

                variant=self.variant(choice,text)

                if choice.get("variants") and not variant:

                    state.pending={"kind":"variant","item_id":choice["id"],"quantity":pending.get("quantity",1)}

                    return f"The lowest-priced available option is {choice['name']}. Which size would you like?"

                return self.add(state,choice,variant,pending.get("quantity",1),pending_selection=True)

        choice=None

        number=re.search(r"\b(?:number )?(\d+)\b|\b(first|second|third|fourth|fifth|sixth|seventh|1st|2nd|3rd|4th|5th|6th|7th)\b",text.lower())

        if number:

            raw=number.group(1) or str(ORDINALS[number.group(2)]); idx=int(raw)-1

            if 0<=idx<len(choices):choice=choices[idx]

        if not choice:

            by_price=re.search(r"(?:rs\.?\s*)?(\d{2,5})",text.lower())

            if by_price: choice=next((x for x in choices if round(self.price(x))==int(by_price.group(1))),None)

        if not choice:

            found=self.match(text,choices); choice=found[0] if len(found)==1 else None

        if pending["kind"]=="item":

            if not choice:return "Please choose one of the numbered available options."

            variant=self.variant(choice,text)

            if choice.get("variants") and not variant:

                state.pending={"kind":"variant","item_id":choice["id"],"quantity":pending.get("quantity",1)}

                return f"Which size for {choice['name']}?\n"+"\n".join(f"- {v['name']} — Rs. {money(v['price']):.0f}" for v in choice["variants"])

            state.pending=None; return self.add(state,choice,variant,pending.get("quantity",1),pending_selection=True)

        item=next((x for x in self.menu if x["id"]==pending["item_id"]),None)

        if not item:return "That choice is no longer available. Please choose another item."

        variant=self.variant(item,text)

        if not variant:return "Please choose one of the available sizes shown."

        state.pending=None; return self.add(state,item,variant,pending.get("quantity",1),pending_selection=True)



    def respond(self,state:AssistantState,text:str,interpretation:Interpretation|None=None)->tuple[str,bool]:

        raw=text.strip(); low=norm(raw)

        is_add=bool(re.search(r"\b(add|give|want|need|chahiye|chahye|kro|kar do|order)\b",raw,re.I))

        # A local read-only/security signal is a veto, not a competing model

        # guess. This prevents a malformed provider response from turning a

        # budget question into an action.

        fallback=interpret_fallback(raw)

        # Local rules are only safety/read-only vetoes. They must not replace a

        # valid Groq recommendation or a contextual order interpretation.

        if fallback.intent in {"SECURITY_MANIPULATION","CORRECTION_COMPLAINT","CANCEL_PENDING_REQUEST","MENU_FILTER"}:

            interpretation=fallback

        if len(self.category_slugs(raw, fallback)) > 1 and re.search(r"\b(show|list|dikha\w*|alag)\b", low):

            interpretation=Interpretation("MENU_QUERY",False,.95,category_slugs=tuple(self.category_slugs(raw, fallback)))

        # A clearly named, available product with an explicit ordering request
        # must not be downgraded to a broad category browse by the planner.
        # This is a narrowly scoped safety/consistency guard, not a competing
        # fuzzy intent classifier: only an exact live-menu name qualifies.
        named_items = self.exact_mentions(raw)
        explicit_order = bool(re.search(
            r"\b(?:add|order|i\s+want(?:\s+to\s+order)?|i\s+would\s+like\s+to\s+order|give\s+me|chahiye|chahye)\b",
            raw, re.I,
        ))
        informational = bool(re.search(
            r"\b(?:how much|what(?:'s| is) the price|price|recommend|suggest|show|list|available|do you have)\b|\?",
            raw, re.I,
        ))
        if (len(named_items) == 1 and explicit_order and not informational
                and interpretation is not None
                and interpretation.intent in {"MENU_QUERY", "ITEM_DETAILS", "PRICE_QUERY", "UNKNOWN"}):
            logger.info("assistant_named_order_routing intent_from=%s intent_to=ADD_ITEM", interpretation.intent)
            interpretation = Interpretation("ADD_ITEM", True, .95)

        self.begin(raw,interpretation)

        interpretation=self._interpretation

        if not raw:return "Please type what you would like to ask or add.",False

        if interpretation.intent=="CORRECTION_COMPLAINT": return "You’re right — I only change the draft when you clearly ask me to. Your cart is unchanged.",False

        if interpretation.intent=="CANCEL_PENDING_REQUEST":

            if state.pending: state.pending=None; return "No problem — I cancelled that selection. Your existing draft cart is unchanged.",False

            return "There is no pending selection to cancel. Your draft cart is unchanged.",False

        # Read-only requests always win over a pending selection. This happens

        # before any option resolver so a budget number can never become an add.

        slugs=self.category_slugs(raw,interpretation)

        exact_ids=set(interpretation.item_ids)

        exact_ids.update(x["id"] for x in self.menu if norm(x["name"]) in low)

        if interpretation.intent in {"MENU_FILTER","MENU_QUERY","ITEM_DETAILS","PRICE_QUERY","PRICE_COMPARISON","RECOMMENDATION"}:

            if interpretation.budget is not None:

                source=[x for x in self.menu if not slugs or x.get("category_slug") in slugs]

                affordable=[x for x in source if self.price(x)<=interpretation.budget]

                return ("Available under that amount:\n"+self.render_options(affordable)) if affordable else "There are no currently available items under that amount.",False

            if len(exact_ids)==1 and (QUESTION_WORDS.search(raw) or interpretation.intent in {"ITEM_DETAILS","PRICE_QUERY"}):

                item=next(x for x in self.menu if x["id"] in exact_ids)

                if item.get("variants") and not interpretation.variant_id:

                    return f"{item['name']} sizes:\n"+"\n".join(f"- {v['name']} — Rs. {money(v['price']):.0f}" for v in item["variants"]),False

                return f"{item['name']} is available for Rs. {self.price(item):.0f}.",False

            if interpretation.intent!="RECOMMENDATION" and self.unavailable_specific_request(raw,slugs):

                return "That specific item is not currently available on Pizza Point’s menu. I can show verified available alternatives if you tell me the category you prefer.",False

            if "cheese" in low:

                source=[x for x in self.menu if not slugs or x.get("category_slug") in slugs]

                cheese=[x for x in source if "cheese" in norm(x["name"])]

                return ("Available cheese options:\n"+self.render_options(cheese)) if cheese else "No matching cheese option is currently available.",False

            # Gemini recommendations are rendered only from validated live IDs.

            # We deliberately do not infer ingredients, popularity or discounts.

            if interpretation.intent=="RECOMMENDATION":

                suggested=[x for x in self.menu if x["id"] in interpretation.item_ids]

                if suggested:return "Based on the current menu, you could consider:\n"+self.render_options(suggested),False

                return "I can recommend from the current menu, but I need a preference such as pizza, burger, shawarma, budget, or cheese.",False

            if interpretation.intent=="PRICE_COMPARISON" and interpretation.item_ids:

                compared=[x for x in self.menu if x["id"] in interpretation.item_ids]

                if compared:return "Current prices:\n"+self.render_options(compared),False

            if len(slugs)>1:

                state.pending={"kind":"item","item_ids":[x["id"] for x in self.menu if x.get("category_slug") in slugs],"quantity":1}

                return self.render_categories(slugs),False

            if slugs and interpretation.intent in {"MENU_QUERY","RECOMMENDATION"}:

                items=[x for x in self.menu if x.get("category_slug") in slugs]

                state.pending={"kind":"item","item_ids":[x["id"] for x in items],"quantity":1}

                return "Available options:\n"+self.render_options(items),False

            if interpretation.intent=="MENU_QUERY" and re.search(r"\b(delivery|pickup|charges?|hours?|opening|policy|payment)\b",low):

                return "I can only confirm information that is available on Pizza Point’s current menu. Ask me about a menu category, item, price, or your draft order.",False

        # A comparison is informational. Resolve it against the last live option

        # list, but never pass it to pending selection/addition.

        if interpretation.intent=="PRICE_COMPARISON" and not (state.pending and re.fullmatch(r"\s*(cheapest|sasta|cheaper)\s+one\s*",low)):

            choices=[x for x in self.menu if x["id"] in (state.pending or {}).get("item_ids",[])] or self.menu

            cheapest=min(choices,key=self.price) if choices else None

            return (f"The lowest-priced available option is {cheapest['name']} — Rs. {self.price(cheapest):.0f}.") if cheapest else "There are no available options to compare.",False

        if INJECTION.search(raw): return "I can only help with Pizza Point’s current menu and your own draft order. Prices, access, and orders stay protected.",False

        if re.search(r"\b(weather|president|math|python|cricket|essay|joke|dating)\b",low): return "I’m here to help with Pizza Point’s menu and draft order. What would you like to order?",False

        if re.search(r"\b(biryani|sushi|coffee|beef|fake)\b",low): return "That is not currently on the Pizza Point menu. I can show real available options instead.",False

        requested_deal=re.search(r"\bdeal\s*(\d+)\b",low)

        if requested_deal and not any(norm(x["name"])==f"deal {requested_deal.group(1)}" for x in self.menu): return "That deal is not currently available. I can show the live deals on the menu.",False

        if RESET.search(raw) and self.allowed("CLEAR_CART",state): state.lines=[];state.pending=None;state.context={}; return "Your draft cart is cleared. We can start a new order whenever you’re ready.",True

        if UNDO.search(raw) and self.allowed("UNDO",state): return "__UNDO__",False

        for kind,pattern in ORDER_TYPE.items():

            if pattern.search(raw) and self.allowed("SET_ORDER_TYPE",state):

                state.order_type=kind

                if kind=="delivery" and not state.delivery_address:return "Delivery selected. Please share your delivery address when you are ready; this is still only a draft.",True

                return f"{kind.title()} selected for this draft. No real order has been created.",True

        if (low.startswith("address ") or low.startswith("address:")) and self.allowed("SET_ADDRESS",state):

            state.delivery_address=raw.split(":",1)[-1].replace("address", "",1).strip(); return "Saved the delivery address to this draft only.",True

        # New add request supersedes a pending selection.

        # An explicit ordering verb wins over descriptive words such as

        # "cheapest"; budget/price questions are handled separately below.

        if not is_add and re.search(r"\b(cart|summary|total|kitna bana|kitna total|kitna hua|how many|what.?s left|what is left|what did i order|show (?:my )?order|kya bacha hai|cart dikhao)\b",low):

            draft=self.draft(state); return ("Your draft cart is empty." if not draft["items"] else "Draft total: Rs. %.0f (%s item%s)."%(draft["total"],draft["count"],"s" if draft["count"]!=1 else "")),False

        # A pending choice is contextual, never a lock. Live-menu questions and

        # a new category request are handled first; only a genuine answer falls

        # through to pending resolution.

        # Details/questions about an ordinal option must never select or add it.

        if state.pending and re.search(r"\b(show|what|details|how much|price|kitne)\b",low) and re.search(r"\b(first|second|third|fourth|fifth|sixth|seventh|\d+(?:st|nd|rd|th)?|number)\b",low):

            choices=[x for x in self.menu if x["id"] in state.pending.get("item_ids",[])]

            ordinal=next((ORDINALS[w] for w in ORDINALS if re.search(rf"\b{re.escape(w)}\b",low)),None)

            numeric=re.search(r"\b(?:number )?(\d+)\b",low); ordinal=ordinal or (int(numeric.group(1)) if numeric else None)

            if ordinal and ordinal<=len(choices):

                item=choices[ordinal-1]; return f"{item['name']} — Rs. {self.price(item):.0f}. Say “add {ordinal}” if you would like it.",False

            return "That option number is not in the current list.",False

        if state.pending and (QUESTION_WORDS.search(raw) or (self.categories(raw) and not re.search(r"\b(first|second|third|fourth|fifth|sixth|seventh|number|rs\.?\s*\d+)\b",low))):

            cats=self.categories(raw)

            if cats:

                state.pending={"kind":"item","item_ids":[x["id"] for x in cats],"quantity":qty_from(raw)}

                return "Available options:\n"+self.render_options(cats),False

            if re.search(r"\b(what else|aur kya|kuch aur|something else)\b",low):

                return "I can show pizzas, burgers, shawarma, fries, pasta, or deals. Which category would you like?",False

        if state.pending and not is_add:

            answer=self.resolve_pending(state,raw)

            if answer:return answer, answer.startswith("Added")

        if REMOVE_WORDS.search(raw):

            category=self.categories(raw)

            if re.search(r"\b(all|everything)\b",low) and category:return self.remove(state,raw,all_category=True),True

            matches=self.match(raw)

            if matches:return self.remove(state,raw,qty_from(raw,1) if re.search(r"\b(one|aik|ek|two|three|four|five|\d+)\b",low) else None),True

            if category:return self.remove(state,raw,all_category=True),True

            if state.context.get("last_item_id"):

                item=next((x for x in self.menu if x["id"]==state.context["last_item_id"]),None)

                return self.remove(state,item["name"] if item else raw),True

        # explicit quantity change for last/identified line

        if re.search(r"\b(make|krdo|kar do|change)\b",low) and re.search(r"\b\d+\b",low):

            matches=self.match(raw); target=matches[0] if len(matches)==1 else next((x for x in self.menu if x["id"]==state.context.get("last_item_id")),None)

            if target:

                lines=[x for x in state.lines if x.item_id==target["id"]]

                if len(lines)==1 and self.allowed("CHANGE_QUANTITY",state): lines[0].quantity=qty_from(raw); return "Updated the quantity in your draft cart.",True

        # Natural repeat and one-less references use the persisted last item.

        if re.search(r"\b(same again|one more|add another|aik aur)\b",low) and state.context.get("last_item_id"):

            item=next((x for x in self.menu if x["id"]==state.context["last_item_id"]),None); variant_id=state.context.get("last_variant_id")

            variant=next((v for v in (item or {}).get("variants",[]) if v["id"]==variant_id),None)

            if item:return self.add(state,item,variant,1),True

        if re.search(r"\b(one less|aik kam|ek kam)\b",low) and state.context.get("last_item_id"):

            item=next((x for x in self.menu if x["id"]==state.context["last_item_id"]),None)

            if item:return self.remove(state,item["name"],1),True

        # Change only the last unambiguous selected variant; never guess a line.

        if re.search(r"\b(small|medium|large|family)\b",low) and re.search(r"\b(change|make|krdo|kar do|instead|wala)\b",low):

            item=next((x for x in self.menu if x["id"]==state.context.get("last_item_id")),None)

            new_variant=self.variant(item,raw) if item else None

            matches=[x for x in state.lines if item and x.item_id==item["id"]]

            if item and new_variant and len(matches)==1 and self.allowed("CHANGE_VARIANT",state):

                matches[0].variant_id=new_variant["id"]; state.context["last_variant_id"]=new_variant["id"]

                return f"Changed {item['name']} to {new_variant['name']}.",True

        # menu/price questions always remain read-only

        limit=re.search(r"(?:under|below)\s*(?:rs\.?\s*)?(\d+)",low)

        if limit:

            cats=self.categories(raw); source=cats or self.menu

            affordable=[x for x in source if self.price(x)<=int(limit.group(1))]

            return ("Available under that amount:\n"+self.render_options(affordable)) if affordable else "There are no currently available items under that amount.",False

        if QUESTION_WORDS.search(raw) and not is_add:

            matches=self.match(raw)

            cats=self.categories(raw)

            if re.search(r"\b(what.*available|what do you have)\b",low): return "Available now:\n"+self.render_options(self.menu),False

            if "cheese" in low:

                cheese=[x for x in (cats or self.menu) if "cheese" in norm(x["name"])]

                return ("Available cheese options:\n"+self.render_options(cheese)) if cheese else "I can only confirm cheese from current menu names; no matching available item is listed.",False

            exact=[x for x in self.menu if norm(x["name"]) in low]

            if len(exact)==1:return f"{exact[0]['name']} is available for Rs. {self.price(exact[0]):.0f}.",False

            if cats and (re.search(r"\b(show|what|available|have)\b",low) or not matches):

                state.pending={"kind":"item","item_ids":[x["id"] for x in cats],"quantity":1}

                return "Available options:\n"+self.render_options(cats),False

            if len(matches)==1:

                item=matches[0]

                if item.get("variants"): return f"{item['name']} sizes:\n"+"\n".join(f"- {v['name']} — Rs. {money(v['price']):.0f}" for v in item["variants"]),False

                return f"{item['name']} is available for Rs. {self.price(item):.0f}.",False

            # A specific live name such as “Special Deal” must beat its broad category.

            return "I couldn’t find that on the current Pizza Point menu. Try asking for a category such as pizzas, burgers, fries, pasta, or deals.",False

        if is_add and self.allowed("ADD_ITEM",state):

            candidates=self.match(raw)

            categories=self.categories(raw)

            generic_tokens={term for terms in CATEGORY_WORDS.values() for term in terms} | {"chicken","with"}

            if is_add and re.search(r"\b(cheapest|sasta|cheaper)\b",low):

                pool=categories or self.menu

                if "cheese" in low: pool=[x for x in pool if "cheese" in norm(x["name"])]

                if pool:

                    cheapest=min(self.price(x) for x in pool); tied=[x for x in pool if self.price(x)==cheapest]

                    if len(tied)==1:

                        item=tied[0]; variant=self.variant(item,raw)

                        if item.get("variants") and not variant:

                            state.pending={"kind":"variant","item_id":item["id"],"quantity":qty_from(raw)}

                            return f"{item['name']} is the lowest-priced available option. Which size would you like?",True

                        return self.add(state,item,variant,qty_from(raw)),True

                    state.pending={"kind":"item","item_ids":[x["id"] for x in tied],"quantity":qty_from(raw)}

                    return "These are tied for the lowest price. Which would you like?\n"+self.render_options(tied),True

            recognised_specific=any(SequenceMatcher(None,word,token).ratio()>=.84 for item in self.menu for word in low.split() for token in norm(item["name"]).split() if token not in generic_tokens)

            if is_add and categories and not recognised_specific and not self.exact_mentions(raw):

                state.pending={"kind":"item","item_ids":[x["id"] for x in categories],"quantity":qty_from(raw)}

                return "Sure! Which one would you like?\n"+self.render_options(categories),True

            # Multiple clearly named products can share one turn. Each is still

            # independently matched against live data; an item needing a variant

            # pauses safely after earlier unambiguous additions.

            # Only independently exact product mentions may be a multi-item

            # order. Fuzzy candidates are never silently added together.

            unique=self.action_mentions(raw)

            if len(unique)>1 and re.search(r"\b(and|aur)\b",low):

                replies=[]

                for item in unique:

                    variant=self.variant(item,raw)

                    if item.get("variants") and not variant:

                        state.pending={"kind":"variant","item_id":item["id"],"quantity":1}; replies.append(f"Added choices noted for {item['name']}; which size would you like?"); break

                    replies.append(self.add(state,item,variant,qty_from(raw) if item["id"]==unique[0]["id"] else 1))

                return " ".join(replies),True

            # generic category request gets live list, never a guessed product

            if categories and (not candidates or all(norm(x['name']) not in low for x in candidates)):

                state.pending={"kind":"item","item_ids":[x["id"] for x in categories],"quantity":qty_from(raw)}

                return "Sure! Which one would you like?\n"+self.render_options(categories),True

            if len(candidates)==1:

                item=candidates[0]; variant=self.variant(item,raw)

                if item.get("variants") and not variant:

                    state.pending={"kind":"variant","item_id":item["id"],"quantity":qty_from(raw)}

                    return f"Which size for {item['name']}?\n"+"\n".join(f"- {v['name']} — Rs. {money(v['price']):.0f}" for v in item["variants"]),True

                return self.add(state,item,variant,qty_from(raw)),True

            if len(candidates)>1:

                state.pending={"kind":"item","item_ids":[x["id"] for x in candidates],"quantity":qty_from(raw)}

                return "Which item did you mean?\n"+self.render_options(candidates),True

        if re.search(r"\b(hi|hello|salam|assalam|thanks|thank|bye|acha|ok)\b",low):return "Assalamualaikum! I can help with Pizza Point’s current menu and your draft order.",False

        if is_add:return "That is not currently on the Pizza Point menu. I can show real available pizzas, burgers, fries, pasta, or deals.",False

        return "I didn’t catch that. I can help with Pizza Point’s menu, prices, and draft cart.",False



class GroqIntentService:

    """Groq performs language understanding; the engine owns every write."""

    async def hint(self, message: str, menu: list[dict], history: list[dict], draft: dict) -> dict | None:

        key=os.getenv("GROQ_API_KEY","")

        if not key:return None

        model=os.getenv("GROQ_MODEL","openai/gpt-oss-120b")

        text=norm(message)
        exact=[x for x in menu if norm(x["name"]) in text]
        selected={str(x["item_id"]) for x in draft.get("items",[]) if x.get("item_id")}
        selected.update(str(x["id"]) for x in exact)
        slugs=[slug for slug,terms in CATEGORY_WORDS.items() if any(term in text for term in terms)]
        relevant=[x for x in menu if str(x["id"]) in selected]
        relevant += [x for x in menu if x.get("category_slug") in slugs and x not in relevant]
        relevant += [x for x in menu if x not in relevant]
        relevant=relevant[:16]
        allowed=[{"i":x["id"],"n":x["name"],"c":x["category_slug"],"p":money(x.get("base_price") or (x.get("variants") or [{}])[0].get("price")),"v":[{"i":v["id"],"n":v["name"],"p":v["price"]} for v in x.get("variants",[])]} for x in relevant]
        recent=[{"role":x.get("role"),"content":str(x.get("content", ""))[:280]} for x in history[-6:]]
        instruction="Pizza Point intent planner. Return only the schema. Use live IDs only. Questions never mutate. Explicit orders are ADD_ITEM; preserve named item/category and leave omitted size null. Use history for follow-ups. English/Roman Urdu supported."
        context="H:"+json.dumps(recent,separators=(",",":"))+" D:"+json.dumps(draft,separators=(",",":"))+" M:"+json.dumps(allowed,separators=(",",":"))

        # Keep the provider contract deliberately compact. The earlier nested

        # tool-call/reply schema made GPT-OSS structured output unreliable, even

        # though those fields were not used by the cart executor.

        schema={"type":"object","additionalProperties":False,"properties":{"intent":{"type":"string","enum":sorted(VALID_INTENTS)},"mutation_requested":{"type":"boolean"},"item_id":{"type":["string","null"]},"item_ids":{"type":"array","items":{"type":"string"}},"variant_id":{"type":["string","null"]},"category":{"type":["string","null"]},"category_slugs":{"type":"array","items":{"type":"string"}},"quantity":{"type":["integer","null"]},"budget":{"type":["integer","null"]},"option_reference":{"type":["integer","null"]},"order_type":{"type":["string","null"]},"confidence":{"type":"number"}},"required":["intent","mutation_requested","item_id","item_ids","variant_id","category","category_slugs","quantity","budget","option_reference","order_type","confidence"]}

        # GPT-OSS supports strict JSON Schema responses. Sending the schema to

        # Groq prevents model output that is JSON-shaped but fails validation.

        payload={"model":model,"messages":[{"role":"system","content":instruction+"\n"+context},{"role":"user","content":message}],"temperature":0,"max_completion_tokens":256,"response_format":{"type":"json_schema","json_schema":{"name":"pizza_point_intent","strict":True,"schema":schema}}}
        logger.info("assistant_groq_request menu_items=%s history_messages=%s context_chars=%s",len(allowed),len(recent),len(context))

        try:

            # Do not inherit an unrelated local proxy setting.

            async with httpx.AsyncClient(timeout=6, trust_env=False) as client:

                response=await client.post("https://api.groq.com/openai/v1/chat/completions",headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},json=payload)

                if response.status_code==429:return {"provider":"rate_limited"}

                if response.status_code in {401,403}:return {"provider":"permission_denied"}

                if response.status_code==404:return {"provider":"model_unavailable"}

                response.raise_for_status(); text=response.json()["choices"][0]["message"]["content"]

                return json.loads(text)

        except httpx.HTTPStatusError as exc:

            try:

                provider_error=exc.response.json().get("error",{})

            except (ValueError, TypeError):

                provider_error={}

            # Groq's structured error fields contain no credentials or request

            # payload. Keep the provider message bounded so logs remain useful

            # without recording a potentially large diagnostic response.

            error_code=str(provider_error.get("code") or "unknown")[:120]

            error_type=str(provider_error.get("type") or "unknown")[:120]

            error_message=" ".join(str(provider_error.get("message") or "").split())[:300]

            logger.warning("assistant_groq_failure stage=http_status status=%s code=%s type=%s message=%s",exc.response.status_code,error_code,error_type,error_message)

            return {"provider":"invalid_request" if exc.response.status_code == 400 else "unavailable"}

        except json.JSONDecodeError:

            logger.warning("assistant_groq_failure stage=response_json")

            return {"provider":"invalid_response"}

        except (httpx.HTTPError, KeyError, IndexError, TypeError) as exc:

            logger.warning("assistant_groq_failure stage=%s",type(exc).__name__)

            return {"provider":"unavailable"}



class Repository:

    def __init__(self): self.url,self.key=service_settings()

    @property

    def headers(self): return {"apikey":self.key,"Authorization":f"Bearer {self.key}","Content-Type":"application/json","Prefer":"return=representation"}

    async def request(self,method,path,**kwargs):

        # Local proxy variables can be stale or unavailable.  Supabase is a

        # first-party backend dependency, so connect directly just as Groq does.

        async with httpx.AsyncClient(timeout=12, trust_env=False) as client:

            response=await client.request(method,f"{self.url}/rest/v1/{path}",headers=self.headers,**kwargs)

        if response.status_code>=400: raise HTTPException(503,"Assistant draft service is temporarily unavailable")

        return response.json() if response.content else []

    async def menu(self):

        rows=await self.request("GET","menu_items",params={"select":"id,name,description,base_price,is_available,is_active,menu_categories!inner(name,slug,is_active),menu_item_variants(id,name,price,sort_order,is_active)","is_active":"eq.true","is_available":"eq.true","menu_categories.is_active":"eq.true","order":"name.asc"})

        return [{"id":x["id"],"name":x["name"],"description":x.get("description") or "","base_price":x.get("base_price"),"category_name":x["menu_categories"]["name"],"category_slug":x["menu_categories"]["slug"],"variants":[v for v in x.get("menu_item_variants",[]) if v.get("is_active")]} for x in rows]

    async def catalogue(self):
        """Return the complete catalogue for a trusted server integration.

        Unlike ``menu()``, this retains inactive and unavailable rows so the
        caller can make decisions from the published availability fields.
        """
        rows=await self.request("GET","menu_items",params={"select":"id,name,description,base_price,is_available,is_active,menu_categories!inner(id,name,slug,sort_order,is_active),menu_item_variants(id,name,price,sort_order,is_active)","order":"name.asc"})
        return [{
            "id":x["id"],
            "name":x["name"],
            "description":x.get("description") or "",
            "base_price":x.get("base_price"),
            "is_available":x.get("is_available",False),
            "is_active":x.get("is_active",False),
            "category":x.get("menu_categories"),
            "variants":[{
                "id":v["id"], "name":v["name"], "price":v.get("price"),
                "sort_order":v.get("sort_order"), "is_active":v.get("is_active",False),
            } for v in x.get("menu_item_variants",[])],
        } for x in rows]

    async def categories(self):
        rows=await self.request("GET","menu_categories",params={"select":"id,name,slug,sort_order,is_active","is_active":"eq.true","order":"sort_order.asc"})
        return [{"id":x["id"],"name":x["name"],"slug":x["slug"]} for x in rows]

    async def session(self,customer_id):

        rows=await self.request("GET","assistant_sessions",params={"customer_id":f"eq.{customer_id}","select":"*"})

        if rows:return rows[0]

        created=await self.request("POST","assistant_sessions",json={"customer_id":customer_id})

        return created[0]

    async def load(self,session):

        rows=await self.request("GET","assistant_draft_items",params={"session_id":f"eq.{session['id']}","select":"menu_item_id,variant_id,quantity"})

        return AssistantState(session.get("pending"),session.get("context") or {},session.get("order_type"),session.get("delivery_address"),[DraftLine(x["menu_item_id"],x.get("variant_id"),x["quantity"]) for x in rows])

    async def save(self,session,state):

        sid=session["id"]

        await self.request("PATCH","assistant_sessions",params={"id":f"eq.{sid}"},json={"pending":state.pending,"context":state.context,"order_type":state.order_type,"delivery_address":state.delivery_address})

        await self.request("DELETE","assistant_draft_items",params={"session_id":f"eq.{sid}"})

        if state.lines: await self.request("POST","assistant_draft_items",json=[{"session_id":sid,"menu_item_id":x.item_id,"variant_id":x.variant_id,"quantity":x.quantity} for x in state.lines])

    async def message(self,sid,role,content,client_message_id=None): await self.request("POST","assistant_messages",json={"session_id":sid,"role":role,"content":content[:2000],"client_message_id":client_message_id})

    async def prior_reply(self,sid,message_id):

        rows=await self.request("GET","assistant_messages",params={"session_id":f"eq.{sid}","client_message_id":f"eq.{message_id}","role":"eq.customer","select":"created_at","limit":"1"})

        if not rows:return None

        return "That message was already handled; your draft cart has not been changed again."

    async def snapshot(self,sid,state):

        action={"state":{"pending":state.pending,"context":state.context,"order_type":state.order_type,"delivery_address":state.delivery_address,"lines":[x.__dict__ for x in state.lines]}}

        await self.request("POST","assistant_actions",json={"session_id":sid,"action":action})

    async def undo(self,sid):

        rows=await self.request("GET","assistant_actions",params={"session_id":f"eq.{sid}","select":"id,action","order":"created_at.desc","limit":"1"})

        if not rows:return None

        await self.request("DELETE","assistant_actions",params={"id":f"eq.{rows[0]['id']}"})

        state=rows[0]["action"]["state"]; return AssistantState(state.get("pending"),state.get("context") or {},state.get("order_type"),state.get("delivery_address"),[DraftLine(**x) for x in state.get("lines",[])])

    async def messages(self,sid): return await self.request("GET","assistant_messages",params={"session_id":f"eq.{sid}","select":"role,content,created_at","order":"created_at.asc","limit":"50"})

    async def reset_conversation(self,session):

        """Service-role reset is scoped to the authenticated customer's session."""

        sid=session["id"]

        await self.request("DELETE","assistant_messages",params={"session_id":f"eq.{sid}"})

        await self.request("DELETE","assistant_actions",params={"session_id":f"eq.{sid}"})

        await self.save(session,AssistantState())



class MessageIn(BaseModel):

    message: str = Field(min_length=1,max_length=2000)

    message_id: str | None = Field(default=None,max_length=120)



def result(engine,state,reply,messages=None): return {"reply":reply,"draft":engine.draft(state),"pending":state.pending,"order_type":state.order_type,"delivery_address":state.delivery_address,"messages":messages or []}


MAX_MENU_RESULTS=25
FOOD_KEYWORDS={
    "pizza":{"pizza","pizzas","piza","pizz"},
    "burger":{"burger","burgers","burgur"},
    "drink":{"drink","drinks","beverage","beverages","soda","soft drink","soft drinks"},
    "shawarma":{"shawarma","shawarmas","shawrma"},
    "pasta":{"pasta","pastas"},
    "fries":{"fries","fry","sides","side"},
    "deal":{"deal","deals","offer","offers"},
    "roll":{"roll","rolls","paratha","paratha roll","paratha rolls"},
}

def menu_terms(value: str) -> set[str]:
    """Normalize common singular/plural food terms without inventing results."""
    value=norm(value)
    return {canonical for canonical,aliases in FOOD_KEYWORDS.items()
            if value in aliases or any(alias in value.split() for alias in aliases if " " not in alias)}

def matches_menu_category(item: dict, category: str) -> bool:
    item_category=item.get("category") or {}
    source=" ".join(str(item_category.get(key) or "") for key in ("name","slug"))
    wanted=norm(category)
    source_normalized=norm(source)
    if wanted==source_normalized or wanted in {norm(item_category.get("name") or ""),norm(item_category.get("slug") or "")}:
        return True
    return bool(menu_terms(category) & menu_terms(source))

def matches_menu_search(item: dict, search: str) -> bool:
    item_category=item.get("category") or {}
    haystack=norm(" ".join((item.get("name") or "",item_category.get("name") or "",item_category.get("slug") or "")))
    needle=norm(search)
    if not needle:
        return True
    if needle in haystack:
        return True
    # Plural and common food-word searches are matched only against values
    # already present in the Supabase result.
    return bool(menu_terms(search) & menu_terms(haystack))

def compact_menu_item(item: dict) -> dict:
    """Use the same variant-over-base-price representation as ordering."""
    category=item.get("category") or {}
    variants=sorted(
        (variant for variant in item.get("variants",[]) if variant.get("is_active")),
        key=lambda variant: variant.get("sort_order") or 0,
    )
    return {
        "id":item["id"],
        "name":item["name"],
        "category":category.get("name") or category.get("slug") or "Uncategorized",
        "price":item.get("base_price"),
        "variants":[{"id":variant["id"],"name":variant["name"],"price":variant.get("price")} for variant in variants],
        "available":bool(item.get("is_active") and item.get("is_available") and category.get("is_active")),
    }

PIZZA_DIAMETER_SIZE=re.compile(r"\b\d{1,2}\s*(?:[\"″]|inch(?:es)?\b|in\b)",re.I)

def is_pizza_add_on(item: dict) -> bool:
    """Current catalogue add-ons share Pizza category but have no pizza diameter."""
    category=item.get("category") or {}
    category_text=norm(" ".join(str(category.get(key) or "") for key in ("name","slug")))
    variants=item.get("variants",[])
    return "pizza" in category_text and bool(variants) and not any(
        PIZZA_DIAMETER_SIZE.search(str(variant.get("name") or "")) for variant in variants
    )

def cheapest_available_offers(items: list[dict], category: str | None = None) -> list[dict]:
    """Return every tied lowest priced, actually purchasable menu offer.

    An item with variants is purchasable only through one of its active variants,
    matching the browser cart's pricing and validation rules.
    """
    offers=[]
    for item in items:
        menu_category=item.get("category") or {}
        if not (item.get("is_active") and item.get("is_available") and menu_category.get("is_active")):
            continue
        if is_pizza_add_on(item):
            continue
        if category and not matches_menu_category(item,category):
            continue
        common={"id":item["id"],"name":item["name"],"category":menu_category.get("name") or menu_category.get("slug") or "Uncategorized"}
        variants=[variant for variant in item.get("variants",[]) if variant.get("is_active") and variant.get("price") is not None]
        if variants:
            offers.extend({**common,"variant":{"id":variant["id"],"name":variant["name"]},"price":variant["price"]} for variant in variants)
        elif item.get("base_price") is not None:
            offers.append({**common,"variant":None,"price":item["base_price"]})
    if not offers:
        return []
    lowest=min(offer["price"] for offer in offers)
    return [offer for offer in offers if offer["price"]==lowest]

@router.get("/menu")
async def get_menu_for_integration(
    category: str | None = Query(default=None, min_length=1, max_length=80),
    search: str | None = Query(default=None, min_length=1, max_length=120),
    limit: int | None = Query(default=None, ge=1, le=MAX_MENU_RESULTS),
    offset: int = Query(default=0, ge=0),
    _:None=Depends(require_assistant_menu_key),
):
    """Read-only, compact menu feed for trusted n8n integrations."""
    items=await Repository().catalogue()
    if category:
        items=[item for item in items if matches_menu_category(item,category)]
    if search:
        items=[item for item in items if matches_menu_search(item,search)]
    total=len(items); page_size=limit or total; page=items[offset:offset+page_size]
    next_offset=offset+len(page)
    return {"items":[compact_menu_item(item) for item in page],"total":total,"returned":len(page),"offset":offset,"has_more":next_offset<total,"next_offset":next_offset if next_offset<total else None}

@router.get("/menu/categories")
async def get_menu_categories_for_integration(_:None=Depends(require_assistant_menu_key)):
    """Compact, real category list for browsing requests and n8n tool calls."""
    return {"categories":await Repository().categories()}

@router.get("/menu/cheapest")
async def get_cheapest_menu_offers_for_integration(
    category: str | None = Query(default=None, min_length=1, max_length=80),
    _:None=Depends(require_assistant_menu_key),
):
    """Small, real-data response for cheapest-menu questions from n8n."""
    return {"items":cheapest_available_offers(await Repository().catalogue(),category)}



@router.get("/state")

async def get_state(profile:CurrentProfile=Depends(require_roles("customer"))):

    repo=Repository(); session=await repo.session(profile.id); menu=await repo.menu(); state=await repo.load(session)

    return result(Engine(menu),state,"",await repo.messages(session["id"]))



@router.post("/messages")

async def send_message(body:MessageIn,profile:CurrentProfile=Depends(require_roles("customer"))):

    repo=Repository(); session=await repo.session(profile.id); menu=await repo.menu(); engine=Engine(menu); state=await repo.load(session)

    # Message id makes browser retry safe without trusting a client action.

    if body.message_id:

        prior=await repo.prior_reply(session["id"],body.message_id)

        if prior:return result(engine,state,prior,await repo.messages(session["id"]))

    before=AssistantState(state.pending,dict(state.context),state.order_type,state.delivery_address,[DraftLine(x.item_id,x.variant_id,x.quantity) for x in state.lines])

    history=await repo.messages(session["id"])

    hint=await GroqIntentService().hint(body.message,menu,history,engine.draft(state))

    interpretation=validate_groq_payload(hint,menu)

    if not interpretation:

        provider=hint.get("provider") if isinstance(hint,dict) else "unavailable"

        # A provider outage must not erase a clear, locally-verifiable request.

        # The executor still requires explicit action language and resolves all

        # items/variants from the live menu, so this path cannot invent a cart

        # operation. Ambiguous language remains a clarification, never an add.

        safe_fallback=interpret_fallback(body.message)

        if safe_fallback.intent not in {"UNKNOWN","GREETING","THANKS"} or state.pending:

            reply,changed=engine.respond(state,body.message,safe_fallback)

            logger.warning("assistant_request_degraded stage=groq provider=%s intent=%s",provider,safe_fallback.intent)

        else:

            changed=False

            message={

                "permission_denied":"The intelligent ordering assistant is temporarily unavailable because its AI service access needs attention. Your draft cart has not been changed.",

                "model_unavailable":"The intelligent ordering assistant is temporarily unavailable while its AI model configuration is updated. Your draft cart has not been changed.",

                "rate_limited":"The intelligent ordering assistant is temporarily busy. Your draft cart has not been changed; please try again shortly.",

                "invalid_request":"The intelligent ordering assistant is temporarily unavailable while its AI configuration is updated. Your draft cart has not been changed.",

                "invalid_response":"The intelligent ordering assistant returned an invalid response. Your draft cart has not been changed.",

            }.get(provider,"The intelligent ordering assistant is temporarily unavailable. Your draft cart has not been changed. Please try again shortly.")

            logger.warning("assistant_request_unavailable stage=groq provider=%s",provider)

            reply=message

    else:

        # The provider supplies language understanding only.  Rendering and

        # all changes are independently resolved from this live menu snapshot.

        # Thus a plausible model reply/tool proposal cannot invent a product,

        # price, variant, or mutate a cart without explicit customer language.

        reply,changed=engine.respond(state,body.message,interpretation)

    if reply=="__UNDO__":

        restored=await repo.undo(session["id"])

        if not restored: reply="There is no earlier draft-cart change to undo."; changed=False

        else: state=restored; reply="Undid the previous draft-cart change."; changed=True

    if changed and reply!="__UNDO__": await repo.snapshot(session["id"],before)

    # Provider trouble cannot destroy state; deterministic grounding remains available.

    if hint and hint.get("provider") in {"rate_limited","unavailable"} and reply.startswith("I didn’t catch"):

        reply="I’m having trouble understanding that right now. Your draft cart is safe — please try again."

    state.context["last_message_id"]=body.message_id; state.context["last_reply"]=reply

    await repo.save(session,state); await repo.message(session["id"],"customer",body.message,body.message_id); await repo.message(session["id"],"assistant",reply)

    return result(engine,state,reply,await repo.messages(session["id"]))



@router.post("/reset")

async def reset(profile:CurrentProfile=Depends(require_roles("customer"))):

    repo=Repository(); session=await repo.session(profile.id); state=AssistantState(); await repo.reset_conversation(session)

    return result(Engine(await repo.menu()),state,"",[])
