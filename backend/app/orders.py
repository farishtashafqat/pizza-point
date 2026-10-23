"""Authenticated Phase 4 order API. The database RPC repeats validation atomically."""
from typing import Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator, model_validator

from .auth import CurrentProfile, get_current_profile, settings

router = APIRouter(prefix="/orders", tags=["orders"])

class OrderLineRequest(BaseModel):
    menu_item_id: UUID
    variant_id: UUID | None = None
    quantity: int = Field(ge=1, le=99)

class CreateOrderRequest(BaseModel):
    order_type: Literal["delivery", "pickup"]
    customer_name: str = Field(min_length=1, max_length=120)
    phone: str
    delivery_address: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=1000)
    payment_method: Literal["cash_on_delivery", "pay_at_restaurant"]
    idempotency_key: UUID
    items: list[OrderLineRequest] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def validate_checkout(self):
        if self.order_type == "delivery":
            if not self.delivery_address or not self.delivery_address.strip() or self.payment_method != "cash_on_delivery":
                raise ValueError("Delivery requires an address and cash on delivery")
        elif self.delivery_address or self.payment_method != "pay_at_restaurant":
            raise ValueError("Pickup does not use a delivery address and is paid at restaurant")
        return self

    @field_validator("phone")
    @classmethod
    def normalize_pakistani_mobile(cls, value: str) -> str:
        value = value.strip()
        if value.startswith("+923") and len(value) == 13 and value[1:].isdigit():
            return "0" + value[3:]
        if len(value) == 11 and value.startswith("03") and value.isdigit():
            return value
        raise ValueError("Enter a Pakistani mobile number as 03XXXXXXXXX or +923XXXXXXXXX")

def auth_headers(token: str, key: str) -> dict[str, str]:
    return {"apikey": key, "Authorization": f"Bearer {token}", "Content-Type": "application/json"}

async def request_token_from_profile(profile: CurrentProfile = Depends(get_current_profile)) -> CurrentProfile:
    if profile.role != "customer":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only customers can place orders")
    return profile

def require_staff(profile: CurrentProfile = Depends(get_current_profile)) -> CurrentProfile:
    if profile.role not in {"kitchen", "admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Staff access required")
    return profile

def bearer_token(request: Request) -> str:
    value = request.headers.get("authorization", "")
    if not value.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    return value.split(" ", 1)[1]

def order_response(result: object) -> dict:
    """Normalize PostgREST's scalar/composite RPC response and reject malformed data."""
    if isinstance(result, list): result = result[0] if result else None
    if isinstance(result, dict) and "create_customer_order" in result: result = result["create_customer_order"]
    if not isinstance(result, dict) or not {"id", "order_number", "total", "order_type", "status"}.issubset(result):
        raise HTTPException(status_code=502, detail="Order was saved but the order response was malformed")
    return result

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_order(payload: CreateOrderRequest, request: Request, profile: CurrentProfile = Depends(request_token_from_profile)):
    """Check live prices/availability, then call the atomic database transaction."""
    url, key = settings(); token = bearer_token(request); headers = auth_headers(token, key)
    item_ids = ",".join(str(line.menu_item_id) for line in payload.items)
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            items_response = await client.get(f"{url}/rest/v1/menu_items", headers=headers, params={"id": f"in.({item_ids})", "select": "id,base_price,is_active,is_available"})
            variants_response = await client.get(f"{url}/rest/v1/menu_item_variants", headers=headers, params={"item_id": f"in.({item_ids})", "select": "id,item_id,is_active,price"})
            if items_response.status_code != 200 or variants_response.status_code != 200:
                raise HTTPException(status_code=503, detail="Menu is temporarily unavailable")
            items = {row["id"]: row for row in items_response.json()}; variants = {row["id"]: row for row in variants_response.json()}
            for line in payload.items:
                item = items.get(str(line.menu_item_id))
                if not item or not item["is_active"] or not item["is_available"]:
                    raise HTTPException(status_code=409, detail="One or more cart items are unavailable")
                if line.variant_id:
                    variant = variants.get(str(line.variant_id))
                    if not variant or variant["item_id"] != str(line.menu_item_id) or not variant["is_active"]:
                        raise HTTPException(status_code=409, detail="A selected size is unavailable")
                elif any(v["item_id"] == str(line.menu_item_id) and v["is_active"] for v in variants.values()) or item["base_price"] is None:
                    raise HTTPException(status_code=409, detail="A valid size selection is required")
            rpc = await client.post(f"{url}/rest/v1/rpc/create_customer_order", headers={**headers, "Prefer": "return=representation"}, json={
                "p_order_type": payload.order_type, "p_customer_name": payload.customer_name, "p_phone": payload.phone,
                "p_delivery_address": payload.delivery_address, "p_notes": payload.notes, "p_payment_method": payload.payment_method,
                "p_idempotency_key": str(payload.idempotency_key), "p_items": [{"menu_item_id": str(x.menu_item_id), "variant_id": str(x.variant_id) if x.variant_id else None, "quantity": x.quantity} for x in payload.items],
            })
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Order service unavailable")
    if rpc.status_code not in (200, 201):
        raise HTTPException(status_code=409 if rpc.status_code < 500 else 503, detail="Unable to place this order. Please refresh your cart and try again.")
    return order_response(rpc.json())

@router.get("")
async def list_orders(request: Request, profile: CurrentProfile = Depends(get_current_profile)):
    url, key = settings(); token = bearer_token(request)
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(f"{url}/rest/v1/orders", headers=auth_headers(token, key), params={"select": "id,order_number,order_type,customer_name,phone,delivery_address,notes,payment_method,status,total,created_at,order_items(id,item_name,variant_name,quantity,unit_price,line_total)", "order": "created_at.desc"})
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Order service unavailable")
    if response.status_code != 200: raise HTTPException(status_code=503, detail="Orders are temporarily unavailable")
    return response.json()

async def staff_orders(request: Request, profile: CurrentProfile, active_only: bool = False):
    url, key = settings(); token = bearer_token(request); params={"select": "id,order_number,order_type,customer_name,phone,delivery_address,notes,payment_method,status,total,created_at,order_items(id,item_name,variant_name,quantity,unit_price,line_total)", "order": "created_at.desc"}
    if active_only: params["status"] = "in.(Confirmed,Preparing,Ready)"
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(f"{url}/rest/v1/orders", headers=auth_headers(token, key), params=params)
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Order service unavailable")
    if response.status_code != 200: raise HTTPException(status_code=503, detail="Orders are temporarily unavailable")
    return response.json()

@router.get("/admin")
async def admin_orders(request: Request, profile: CurrentProfile = Depends(get_current_profile)):
    if profile.role != "admin": raise HTTPException(status_code=403, detail="Admin access required")
    return await staff_orders(request, profile)

@router.get("/kitchen")
async def kitchen_orders(request: Request, profile: CurrentProfile = Depends(get_current_profile)):
    if profile.role not in {"kitchen", "admin"}: raise HTTPException(status_code=403, detail="Kitchen access required")
    return await staff_orders(request, profile, active_only=True)

class StatusRequest(BaseModel):
    status: Literal["Confirmed", "Rejected", "Preparing", "Ready", "Completed"]

@router.post("/{order_id}/status")
async def update_order_status(order_id: UUID, payload: StatusRequest, request: Request, profile: CurrentProfile = Depends(require_staff)):
    url, key = settings(); token = bearer_token(request)
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.post(f"{url}/rest/v1/rpc/transition_order_status", headers={**auth_headers(token,key),"Prefer":"return=representation"}, json={"p_order_id":str(order_id),"p_status":payload.status})
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Order service unavailable")
    if response.status_code not in (200,201): raise HTTPException(status_code=409 if response.status_code < 500 else 503, detail="This status transition is not permitted")
    result=response.json(); return result[0] if isinstance(result,list) else result

@router.post("/{order_id}/cancel")
async def cancel_order(order_id: UUID, request: Request, profile: CurrentProfile = Depends(request_token_from_profile)):
    url, key = settings(); token = bearer_token(request)
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.post(f"{url}/rest/v1/rpc/cancel_customer_order", headers={**auth_headers(token, key), "Prefer": "return=representation"}, json={"p_order_id": str(order_id)})
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Order service unavailable")
    if response.status_code not in (200, 201): raise HTTPException(status_code=409, detail="This order can no longer be cancelled")
    result = response.json(); return result[0] if isinstance(result, list) else result
