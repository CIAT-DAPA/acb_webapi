from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx
import os
router = APIRouter(prefix="/auth", tags=["Authentication"])

class ClientCredentials(BaseModel):
    client_id: str
    client_secret: str



@router.post("/get-client-token", summary="Get a Keycloak token using client credentials")
async def get_token(body: ClientCredentials):
    KEYCLOAK_BASE_URL = os.getenv("KEYCLOAK_URL")
    REALM = os.getenv("KEYCLOAK_REALM")
    TOKEN_ENDPOINT = f"{KEYCLOAK_BASE_URL}/realms/{REALM}/protocol/openid-connect/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": body.client_id,
        "client_secret": body.client_secret,
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(TOKEN_ENDPOINT, data=data, headers=headers)

    if response.status_code != 200:
        print("Keycloak error:", response.text)
        raise HTTPException(status_code=401, detail="Credenciales inválidas o cliente no existe")

    return response.json()
