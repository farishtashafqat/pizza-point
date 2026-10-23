"""Admin-only staff invitations and lifecycle management via backend service credentials."""
from typing import Literal
import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from .auth import CurrentProfile, require_roles, service_settings

router=APIRouter(prefix="/staff",tags=["staff"])

def service_headers(key:str): return {"apikey":key,"Authorization":f"Bearer {key}","Content-Type":"application/json"}

async def staff_rows(client:httpx.AsyncClient,url:str,key:str):
    response=await client.get(f"{url}/rest/v1/profiles",headers=service_headers(key),params={"role":"in.(admin,kitchen)","select":"id,email,full_name,role,is_active,created_at","order":"role,created_at"})
    if response.status_code!=200: raise HTTPException(status_code=503,detail="Staff directory is unavailable")
    return response.json()

@router.get("")
async def list_staff(profile:CurrentProfile=Depends(require_roles("admin"))):
    url,key=service_settings()
    try:
        async with httpx.AsyncClient(timeout=12) as client: return await staff_rows(client,url,key)
    except httpx.HTTPError: raise HTTPException(status_code=503,detail="Staff directory is unavailable")

class InviteStaffRequest(BaseModel):
    email:str=Field(max_length=254)
    full_name:str=Field(min_length=1,max_length=120)
    role:Literal["admin","kitchen"]
    @field_validator("email")
    @classmethod
    def valid_email(cls,value:str)->str:
        value=value.strip().lower()
        if "@" not in value or value.startswith("@") or value.endswith("@") or " " in value: raise ValueError("Enter a valid email address")
        return value

@router.post("/invite",status_code=status.HTTP_201_CREATED)
async def invite_staff(payload:InviteStaffRequest,profile:CurrentProfile=Depends(require_roles("admin"))):
    url,key=service_settings(); headers=service_headers(key)
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            invite=await client.post(f"{url}/auth/v1/invite",headers=headers,json={"email":str(payload.email),"data":{"full_name":payload.full_name}})
            if invite.status_code not in (200,201): raise HTTPException(status_code=409,detail="Unable to invite this email address")
            user=invite.json().get("user",invite.json()); user_id=user.get("id")
            if not user_id: raise HTTPException(status_code=502,detail="Invitation response did not include a user")
            update=await client.patch(f"{url}/rest/v1/profiles",headers={**headers,"Prefer":"return=representation"},params={"id":f"eq.{user_id}"},json={"full_name":payload.full_name,"role":payload.role,"is_active":True})
            if update.status_code not in (200,204): raise HTTPException(status_code=503,detail="Invitation was created but staff setup could not be completed")
            return update.json()[0] if update.content else {"id":user_id,"email":str(payload.email),"role":payload.role,"is_active":True}
    except httpx.HTTPError: raise HTTPException(status_code=503,detail="Staff invitation service is unavailable")

class ActiveRequest(BaseModel): is_active:bool

@router.patch("/{staff_id}/active")
async def set_staff_active(staff_id:str,payload:ActiveRequest,profile:CurrentProfile=Depends(require_roles("admin"))):
    if staff_id==profile.id and not payload.is_active: raise HTTPException(status_code=409,detail="You cannot deactivate your own account")
    url,key=service_settings(); headers=service_headers(key)
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            lookup=await client.get(f"{url}/rest/v1/profiles",headers=headers,params={"id":f"eq.{staff_id}","select":"id,role,is_active"})
            if lookup.status_code!=200 or not lookup.json(): raise HTTPException(status_code=404,detail="Staff account not found")
            target=lookup.json()[0]
            if target["role"] not in {"admin","kitchen"}: raise HTTPException(status_code=404,detail="Staff account not found")
            if target["role"]=="admin" and not payload.is_active and target["is_active"]:
                admins=await client.get(f"{url}/rest/v1/profiles",headers=headers,params={"role":"eq.admin","is_active":"eq.true","select":"id"})
                if admins.status_code!=200: raise HTTPException(status_code=503,detail="Unable to verify active administrators")
                if len(admins.json())<=1: raise HTTPException(status_code=409,detail="At least one active Admin must remain")
            update=await client.patch(f"{url}/rest/v1/profiles",headers={**headers,"Prefer":"return=representation"},params={"id":f"eq.{staff_id}"},json={"is_active":payload.is_active})
            if update.status_code!=200: raise HTTPException(status_code=503,detail="Unable to update staff account")
            return update.json()[0]
    except httpx.HTTPError: raise HTTPException(status_code=503,detail="Staff management service is unavailable")
