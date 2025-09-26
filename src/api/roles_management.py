from fastapi import APIRouter, HTTPException, Depends, Path, Query
from typing import List, Optional
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from acb_orm.schemas.roles_schema import RolesCreate, RolesRead, RolesUpdate
from services.roles_service import RoleService
from auth.access_utils import get_current_user

router = APIRouter(prefix="/roles", tags=["Role Management"], include_in_schema=False)
service_role = RoleService()
security = HTTPBearer()

@router.post("/", response_model=RolesRead)
def create_role(
    role: RolesCreate = ...,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    return service_role.create(role, user_id)

@router.get("/", response_model=List[RolesRead])
def get_all_roles(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    return service_role.get_all()

@router.get("/{role_id}", response_model=RolesRead)
def get_role_by_id(
    role_id: str = Path(..., description="Role ID"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    return service_role.get_by_id(role_id)

@router.get("/name/{name}", response_model=List[RolesRead])
def get_roles_by_name(
    name: str = Path(..., description="Role name or substring to search for."),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    return service_role.get_by_name(name)

@router.put("/{role_id}", response_model=RolesRead)
def update_role(
    role_id: str = Path(..., description="Role ID to update"),
    role: RolesUpdate = ...,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    return service_role.update(role_id, role, user_id)

# @router.delete("/{role_id}")
# def delete_role(
#     role_id: str = Path(..., description="Role ID to delete"),
#     credentials: HTTPAuthorizationCredentials = Depends(security)
# ):
#     user = get_current_user(credentials)
#     user_id = user["user_db"]["id"]
#     service_role.delete(role_id)
#     return {"success": True}
