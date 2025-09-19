from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError, ExpiredSignatureError
import requests
import os
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(tags=["Authentication"], prefix="/auth")

security = HTTPBearer()

@router.get("/token/validate", summary="Validate a keycloak token")
def validate_local_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    unverified_header = jwt.get_unverified_header(token)

    KEYCLOAK_URL = os.getenv("KEYCLOAK_URL")
    REALM_NAME = os.getenv("KEYCLOAK_REALM")
    CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID")

    jwks_url = f"{KEYCLOAK_URL}/realms/{REALM_NAME}/protocol/openid-connect/certs"
    response = requests.get(jwks_url)
    if response.status_code != 200:
        raise HTTPException(status_code=500, detail="Error fetching JWKS from Keycloak")
    jwks = response.json()

    key = next((k for k in jwks["keys"] if k["kid"] == unverified_header["kid"]), None)
    if not key:
        raise HTTPException(status_code=401, detail="Public key not found")

    try:
        payload = jwt.decode(
            token,
            key,
            algorithms=[unverified_header["alg"]],
            audience="account",
            issuer=f"{KEYCLOAK_URL}/realms/{REALM_NAME}",
        )

        filtered_payload = {
            k: v for k, v in payload.items()
            if k not in ["realm_access", "allowed-origins", "resource_access"]
        }

        client_roles = payload.get("resource_access", {}).get("GanabosquesWeb", {}).get("roles", [])
        filtered_payload["client_roles"] = client_roles

        return {"valid": True, "payload": filtered_payload}

    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Expired token")
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid Token: {str(e)}")

