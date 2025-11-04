# routers/auth.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import requests
import os
from dotenv import load_dotenv

load_dotenv()
#test
router = APIRouter(
    tags=["Authentication"], 
    prefix="/auth", 
)

class LoginRequest(BaseModel):
    username: str
    password: str

@router.post("/login", summary="Autentication with Keycloak", description="Get access and refresh tokens using Keycloak's password grant flow.")
def login(data: LoginRequest):
    KEYCLOAK_URL = os.getenv("KEYCLOAK_URL")
    REALM_NAME = os.getenv("KEYCLOAK_REALM")
    CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID")
    CLIENT_SECRET = os.getenv("KEYCLOAK_CLIENT_SECRET")
    """
    Login endpoint to authenticate users with Keycloak.
    This endpoint uses the password grant type to obtain an access token and a refresh token.

    Require:
    - username
    - password

    Return:
    - access_token
    - refresh_token
    """
    token_url = f"{KEYCLOAK_URL}/realms/{REALM_NAME}/protocol/openid-connect/token"

    payload = {
        "grant_type": "password",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "username": data.username,
        "password": data.password,
    }

    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    response = requests.post(token_url, data=payload, headers=headers)

    if response.status_code != 200:
        raise HTTPException(status_code=401, detail=response.json())

    return response.json()
