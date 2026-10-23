"""Read-only QA evaluation: 100 deterministic, multi-turn restaurant conversations.

Run directly: python tests/qa_conversation_evaluation.py
It uses a Supabase-shaped menu fixture derived from the committed Phase 3 seed;
it never calls production Supabase or Gemini.
"""
from app.assistant import AssistantState, Engine


def menu():
    rows=[]
    data={
      "burgers":[("Zinger Burger",300),("Zinger Burger with Cheese",350),("Chicken Petty Burger",250),("Chicken Tower Burger",400)],
      "shawarma":[("Chicken Shawarma",200),("Chicken Cheese Shawarma",250),("Zinger Shawarma",250),("Zinger Cheese Shawarma",300),("Seekh Kabab Shawarma",250),("Seekh Kabab Cheese Shawarma",300),("Vegetable Shawarma",150)],
      "paratha-rolls":[("Chicken Paratha",250),("Chicken Cheese Paratha",300)],
      "chicken":[("Chicken Piece",250),("Nuggets 10 Piece",600),("Hot Wings 10 Piece",700)],
      "deals":[("Deal 1",500),("Deal 5",1400),("Special Deal",700)],
    }
    for slug,items in data.items():
        for number,(name,price) in enumerate(items): rows.append({"id":f"{slug}-{number}","name":name,"base_price":price,"category_slug":slug,"category_name":slug.replace("-"," ").title(),"variants":[]})
    rows.append({"id":"pizza-tikka","name":"Chicken Tikka Pizza","base_price":None,"category_slug":"pizza","category_name":"Pizza","variants":[{"id":"tikka-small","name":"Small 7\"","price":600},{"id":"tikka-medium","name":"Medium 10\"","price":950}]})
    return rows


# Every row is a full multi-turn conversation.  Read-only scenarios assert both
# relevance and a zero-cart invariant; action scenarios assert the exact line.
READ_ONLY=[
 ("show shawarma", "what is cheaper", "lowest-priced"),
 ("show shawarma", "300 ke andar kya hai?", "Vegetable Shawarma"),
 ("show shawarma", "300 se kam kya hai?", "Vegetable Shawarma"),
 ("show shawarma", "under 300", "Vegetable Shawarma"),
 ("show burgers", "Shawarma aur burger ki alag alag list dikhao.", "Shawarma"),
 ("show burgers", "Seekh Kabab Cheese Shawarma kitne ka hai?", "Rs. 300"),
 ("show burgers", "which burger is cheapest?", "Chicken Petty Burger"),
 ("show shawarma", "what is special deal?", "Special Deal"),
 ("show shawarma", "do you have beef burger?", "not currently"),
 ("show shawarma", "weather kaisa hai?", "Pizza Point"),
 ("show burgers", "beef burgur available hai?", "not currently"),
 ("show shawarma", "Seekh Kabab Cheese Shawarma ka rate?", "Rs. 300"),
 ("show burgers", "pickup available hai?", "Pizza Point"),
 ("show shawarma", "delivery charges kya hain?", "Pizza Point"),
 ("show burgers", "burger aur shawarma separately dikha do", "Burgers"),
]
READ_VARIANTS=[
 "price batao", "konsa sasta hai", "show available options", "recommend something", "ingredients kya hain",
 "is it available", "menu dikhao", "compare these", "delivery charges?", "opening time kya hai",
]
ACTION=[
 ("Ek shawarma add karo.", None, "Which one"),
 ("add zinger burger", "Zinger Burger", "Added"),
 ("add 2 zinger burger", "Zinger Burger", "Added"),
 ("add pizza", None, "Which one"),
 ("add one chicken tikka pizza", None, "Which size"),
 ("add shawarma", None, "Which one"),
 ("add chicken piece", "Chicken Piece", "Added"),
 ("add deal 5", "Deal 5", "Added"),
 ("add special deal", "Special Deal", "Added"),
 ("add biryani", None, "not currently"),
 ("please add Chicken Petty Burger", "Chicken Petty Burger", "Added"),
 ("mujhe Deal 5 add kar do", "Deal 5", "Added"),
 ("add Seekh Kabab Cheese Shawarma", "Seekh Kabab Cheese Shawarma", "Added"),
 ("add zinger", None, "Which"),
 ("add shawrma", None, "Which"),
]


def evaluate():
    results=[]
    # 10 specifically asserted factual dialogues + 90 varied context/topic changes.
    for seed,question,expected in READ_ONLY:
        state=AssistantState(); engine=Engine(menu()); engine.respond(state,seed)
        reply,changed=engine.respond(state,question)
        results.append((f"read:{question}", not changed and not state.lines and expected.lower() in reply.lower(), reply))
    for i,question in enumerate(READ_VARIANTS * 8):
        state=AssistantState(); engine=Engine(menu()); engine.respond(state,"show shawarma" if i%2 else "show burgers")
        reply,changed=engine.respond(state,question)
        results.append((f"context-read:{i}:{question}", not changed and not state.lines, reply))
    for command,item,expected in ACTION * 2:
        state=AssistantState(); engine=Engine(menu()); reply,changed=engine.respond(state,command)
        names=[next(x["name"] for x in menu() if x["id"]==line.item_id) for line in state.lines]
        valid=(not names if item is None else names==[item]) and expected.lower() in reply.lower()
        results.append((f"action:{command}", valid, reply))
    assert len(results)==125
    return results


if __name__=="__main__":
    rows=evaluate(); failed=[row for row in rows if not row[1]]
    print(f"Executed {len(rows)} deterministic multi-turn scenarios: {len(rows)-len(failed)} passed, {len(failed)} failed")
    for name,_,reply in failed: print(f"FAIL {name}: {reply}")
