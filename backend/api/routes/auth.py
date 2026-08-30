"""Authentication and role-based access token endpoints."""

from __future__ import annotations

import base64
import json
import time
import uuid

from fastapi import APIRouter, HTTPException, status

from backend.api.schemas import TokenRequest, TokenResponse
from backend.config import get_settings

router = APIRouter(prefix="/v1/auth", tags=["Auth"])


@router.post("/token", response_model=TokenResponse)
async def generate_token(payload: TokenRequest) -> TokenResponse:
    # Role detection: ISRO evaluator / lead analyst vs demo analyst
    role = "analyst"
    if "isro" in payload.username.lower() or "eval" in payload.username.lower():
        role = "isro_evaluator"
    elif "admin" in payload.username.lower():
        role = "admin"

    # Deterministic token payload
    token_claims = {
        "sub": payload.username,
        "role": role,
        "iss": "satquery-x",
        "iat": int(time.time()),
        "exp": int(time.time()) + 86400,
        "jti": str(uuid.uuid4()),
    }
    encoded = base64.urlsafe_b64encode(json.dumps(token_claims).encode("utf-8")).decode("utf-8")
    token_str = f"sqx.{encoded}.sig"

    return TokenResponse(
        access_token=token_str,
        token_type="bearer",
        role=role,
        expires_in=86400,
    )
