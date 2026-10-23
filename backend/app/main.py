from fastapi import FastAPI
import os
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Depends
from .auth import CurrentProfile, get_current_profile, require_roles
from .orders import router as orders_router
from .staff import router as staff_router
from .assistant import router as assistant_router
from .n8n_bridge import router as n8n_router

app = FastAPI(title="Pizza Point API")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(orders_router)
app.include_router(staff_router)
app.include_router(assistant_router)
app.include_router(n8n_router)

@app.get("/health")
def health():
    return {"status": "ok", "service": "pizza-point-api", "assistant_provider": "groq", "assistant_model": os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")}

def safe_profile(profile: CurrentProfile):
    return {"id": profile.id, "email": profile.email, "full_name": profile.full_name, "role": profile.role}

@app.get("/auth/me")
async def auth_me(profile: CurrentProfile = Depends(get_current_profile)):
    return safe_profile(profile)

@app.get("/auth/customer-test")
async def customer_test(profile: CurrentProfile = Depends(get_current_profile)):
    return {"ok": True, "profile": safe_profile(profile)}

@app.get("/auth/kitchen-test")
async def kitchen_test(profile: CurrentProfile = Depends(require_roles("kitchen", "admin"))):
    return {"ok": True, "profile": safe_profile(profile)}

@app.get("/auth/admin-test")
async def admin_test(profile: CurrentProfile = Depends(require_roles("admin"))):
    return {"ok": True, "profile": safe_profile(profile)}

@app.get("/admin/menu-test")
async def admin_menu_test(profile: CurrentProfile = Depends(require_roles("admin"))):
    """Phase 3 authorization probe; menu administration remains RLS-protected."""
    return {"ok": True, "message": "Admin menu access granted", "profile": safe_profile(profile)}
