from acb_orm.collections.groups import Group
from acb_orm.collections.roles import Role
from fastapi import Depends, HTTPException
from acb_orm.collections.users import User
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError, ExpiredSignatureError
import requests
import os
from dotenv import load_dotenv
from typing import List
from constants.permissions import GLOBAL_ADMIN_ROLE_NAMES, MODULE_ACCESS_CONTROL
from tools.utils import serialize_log

load_dotenv()

# Variables globales para Keycloak
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL")
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM")

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


def get_user_roles_by_group_complet(user_id: str) -> dict:
    """
    Devuelve un diccionario {group_id: role_id} para el usuario.
    """
    user_groups = Group.objects(users_access__user_id=user_id)
    groups_info = []
    for group in user_groups:
        # Buscar el acceso del usuario en el grupo
        user_access = next((ua for ua in group.users_access if str(ua.user_id.id) == str(user_id)), None)
        if user_access:
            role_obj = Role.objects(id=user_access.role_id.id).first()
            groups_info.append({
                "group_id": str(group.id),
                "group_name": group.group_name,
                "role": {
                    "id": str(role_obj.id) if role_obj else None,
                    "role_name": role_obj.role_name if role_obj else None,
                    "permissions": role_obj.permissions if role_obj else {}
                }
            })
    return groups_info

def get_accessible_resources(model, user_id: str):
    """
    Devuelve los recursos accesibles para el usuario (públicos y restringidos por grupo).
    """
    user_groups = get_user_groups(user_id)
    public = model.objects(access_config__access_type="public")
    restricted = model.objects(access_config__access_type="restricted", access_config__allowed_groups__in=user_groups)
    return list(public) + list(restricted)

def user_has_permission(user_id: str, group_id: str, module: str, action: str) -> bool:
    """
    Checks if the user has the required permission (action) for a module in the group.
    :param user_id: User ID
    :param group_id: Group ID
    :param module: Module name (e.g. 'template_management')
    :param action: Action key ('c', 'r', 'u', 'd')
    :return: True if allowed, False otherwise
    """
    # 1. Verificar si el usuario tiene el rol global (superadmin u otros definidos)
    user_groups = Group.objects(users_access__user_id=user_id)
    for group in user_groups:
        for ua in group.users_access:
            if str(ua.user_id.id) == str(user_id):
                role = Role.objects.get(id=ua.role_id.id)
                if role.role_name in GLOBAL_ADMIN_ROLE_NAMES:
                    return True

    # 2. Permiso normal por grupo
    group = Group.objects.get(id=group_id)
    user_access = next((ua for ua in group.users_access if str(ua.user_id.id) == str(user_id)), None)
    if not user_access:
        return False
    role = Role.objects.get(id=user_access.role_id.id)
    return role.permissions.get(module, {}).get(action, False)


def is_superadmin(user_id: str) -> bool:
    """Returns True if user is in any group with a role named in GLOBAL_ADMIN_ROLE_NAMES."""
    user_groups = Group.objects(users_access__user_id=user_id)
    for group in user_groups:
        for ua in group.users_access:
            if str(ua.user_id.id) == str(user_id):
                role_obj = Role.objects(id=ua.role_id.id).first()
                if role_obj and role_obj.role_name in GLOBAL_ADMIN_ROLE_NAMES:
                    return True
    return False

def get_superadmins() -> List[User]:
    """Returns a list of User objects who are superadmins."""
    superadmin_users = set()
    try:
        superadmin_roles = Role.objects(role_name__in=GLOBAL_ADMIN_ROLE_NAMES)
        superadmin_role_ids = [str(role.id) for role in superadmin_roles]

        groups_with_superadmin_roles = Group.objects(users_access__role_id__in=superadmin_role_ids)

        for group in groups_with_superadmin_roles:
            for ua in group.users_access:
                if str(ua.role_id.id) in superadmin_role_ids:
                    user_obj = User.objects(id=ua.user_id.id).first()
                    if user_obj:
                        superadmin_users.add(user_obj)
    except Exception as e:
        #logger.error(f"Error retrieving superadmins: {e}")
        print(f"Error retrieving superadmins: {e}")
        pass
    return list(superadmin_users)

def user_is_group_admin(user_id: str, group_id: str) -> bool:
    """Returns True if the user has role 'admin' in the specified group."""
    try:
        group = Group.objects.get(id=group_id)
    except Exception:
        return False
    for ua in group.users_access:
        if str(ua.user_id.id) == str(user_id):
            role_obj = Role.objects(id=ua.role_id.id).first()
            if role_obj and role_obj.role_name == 'admin':
                return True
    return False


def is_admin(user_id: str) -> bool:
    """Returns True if the user has a role named 'admin' in any group.

    We consider a user an admin if in any group the user's assigned role has
    the name 'admin'. This is used to allow admins to list and manage users
    (except superadmins).
    """
    try:
        user_groups = Group.objects(users_access__user_id=user_id)
    except Exception:
        return False
    for group in user_groups:
        for ua in group.users_access:
            if str(ua.user_id.id) == str(user_id):
                role_obj = Role.objects(id=ua.role_id.id).first()
                if role_obj and role_obj.role_name == 'admin':
                    return True
    return False


def can_assign_superadmin(assigner_user_id: str) -> bool:
    """Only superadmins can assign the superadmin role."""
    return is_superadmin(assigner_user_id)

def get_jwks():
    jwks_url = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/certs"

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
        raise HTTPException(status_code=401, detail="Public key not found")

    try:
        payload = jwt.decode(
            token,
            key,
            algorithms=[unverified_header["alg"]],
            audience="account",
            issuer=f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}",
        )
        ext_id = payload.get("sub")
        user_obj = User.objects(ext_id=ext_id).first()
        if not user_obj:
            # Crear el usuario en la base de datos si no existe
            user_obj = User(
                ext_id=ext_id,
                first_name=payload.get("given_name", ""),
                last_name=payload.get("family_name", ""),
                is_active=True
            )
            user_obj.save()
        if not user_obj.is_active:
            raise HTTPException(status_code=403, detail="User is not active or not authorized")

        payload = {
            k: v for k, v in payload.items()
            if k not in ["realm_access", "allowed-origins", "resource_access"]
        }

        # Construir lista de grupos con roles y permisos
        groups_info = get_user_roles_by_group_complet(user_obj.id)

        payload["user_db"] = {
            "id": str(user_obj.id),
            "is_active": user_obj.is_active,
            "log": serialize_log(user_obj.log),
            "groups": groups_info,
            "is_superadmin": is_superadmin(str(user_obj.id))
        }
        return payload

    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Token inválido: {str(e)}")

