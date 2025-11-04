from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError, ExpiredSignatureError
import requests
import os
from dotenv import load_dotenv

from auth.access_utils import get_current_user

load_dotenv()

router = APIRouter(tags=["Authentication"], prefix="/auth")

security = HTTPBearer()

@router.get("/token/validate", summary="Validate a keycloak token")
def validate_local_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    current_user = get_current_user(credentials)
    return {"valid": True, "payload": current_user}

