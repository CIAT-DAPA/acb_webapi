
# Utilidades para acceso y autorización basadas en la estructura de la base de datos y el ORM
from acb_orm.collections.groups import Group
from acb_orm.collections.roles import Role
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError, ExpiredSignatureError
import requests
import os
from dotenv import load_dotenv
from typing import List

load_dotenv()

security = HTTPBearer()

def get_user_groups(user_id: str) -> list:
    """
    Devuelve una lista de IDs de grupos a los que pertenece el usuario.
    """
    groups = Group.objects(users_access__user_id=user_id)
    return [group.id for group in groups]

def get_user_roles_by_group(user_id: str) -> dict:
    """
    Devuelve un diccionario {group_id: role_id} para el usuario.
    """
    groups = Group.objects(users_access__user_id=user_id)
    roles_by_group = {}
    for group in groups:
        for ua in group.users_access:
            if str(ua.user_id.id) == str(user_id):
                roles_by_group[str(group.id)] = str(ua.role_id.id)
    return roles_by_group

def get_accessible_resources(model, user_id: str):
    """
    Devuelve los recursos accesibles para el usuario (públicos y restringidos por grupo).
    """
    user_groups = get_user_groups(user_id)
    public = model.objects(access_config__access_type="public")
    restricted = model.objects(access_config__access_type="restricted", access_config__allowed_groups__in=user_groups)
    return list(public) + list(restricted)

def user_has_permission(user_id: str, group_id: str, required_permission: str) -> bool:
    """
    Verifica si el usuario tiene el permiso requerido en el grupo.
    """
    group = Group.objects.get(id=group_id)
    user_access = next((ua for ua in group.users_access if str(ua.user_id.id) == str(user_id)), None)
    if not user_access:
        return False
    role = Role.objects.get(id=user_access.role_id.id)
    return required_permission in role.permissions

def get_jwks():
    keycloak_url = os.getenv("KEYCLOAK_URL", "http://localhost:8080")
    realm_name = os.getenv("REALM_NAME", "BulletinBuilder")
    jwks_url = f"{keycloak_url}/realms/{realm_name}/protocol/openid-connect/certs"

    response = requests.get(jwks_url)
    if response.status_code != 200:
        raise HTTPException(status_code=500, detail="No se pudo obtener las claves públicas (JWKS)")
    return response.json()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    token = credentials.credentials
    unverified_header = jwt.get_unverified_header(token)

    jwks = get_jwks()
    key = next((k for k in jwks["keys"] if k["kid"] == unverified_header["kid"]), None)
    if not key:
        raise HTTPException(status_code=401, detail="Clave pública no encontrada")

    keycloak_url = os.getenv("KEYCLOAK_URL", "http://localhost:8080")
    realm_name = os.getenv("REALM_NAME", "BulletinBuilder")

    try:
        payload = jwt.decode(
            token,
            key,
            algorithms=[unverified_header["alg"]],
            audience="account",
            issuer=f"{keycloak_url}/realms/{realm_name}",
        )
        return payload

    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Token inválido: {str(e)}")

