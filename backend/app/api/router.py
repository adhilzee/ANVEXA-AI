from __future__ import annotations

from fastapi import APIRouter

from backend.app.api.endpoints.auth import router as auth_router
from backend.app.api.endpoints.claims import router as claims_router
from backend.app.api.endpoints.citations import router as citations_router
from backend.app.api.endpoints.documents import router as documents_router
from backend.app.api.endpoints.feedback import router as feedback_router
from backend.app.api.endpoints.health import router as health_router
from backend.app.api.endpoints.reports import router as reports_router
from backend.app.api.endpoints.reviews import router as reviews_router
from backend.app.api.endpoints.users import router as users_router
from backend.app.api.endpoints.verification import router as verification_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(documents_router)
api_router.include_router(verification_router)
api_router.include_router(claims_router)
api_router.include_router(citations_router)
api_router.include_router(reviews_router)
api_router.include_router(reports_router)
api_router.include_router(feedback_router)
