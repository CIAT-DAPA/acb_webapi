from fastapi import APIRouter, HTTPException, Depends, Path, Query
from typing import List, Optional
from services.users_service import UsersService
from acb_orm.schemas.users_schema import UsersCreate, UsersUpdate, UsersRead
from auth.access_utils import get_current_user
from auth.access_utils import is_superadmin, is_admin
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

router = APIRouter(prefix="/users", tags=["User Management"])
users_service = UsersService()
security = HTTPBearer()

@router.post("/", response_model=UsersRead)
def create_user(
    user: UsersCreate = ...,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Create a new user document.
    """
    current_user = get_current_user(credentials)
    user_id = current_user["user_db"]["id"]
    return users_service.create(user, user_id)

@router.put("/{user_id}", response_model=UsersRead)
def update_user(
    user_id: str = Path(..., description="Unique identifier of the user to update"),
    user: UsersUpdate = ...,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Update a user by its ID. Log is updated with current user information.
    """
    current_user = get_current_user(credentials)
    updater_user_id = current_user["user_db"]["id"]
    return users_service.update(user_id, user, updater_user_id)

@router.get("/", response_model=List[UsersRead])
def get_all_users(
    active_only: Optional[bool] = Query(None, description="Filter by active status. True=active only, False=inactive only, None=all"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Return all users. Can filter by active status using the query parameter.
    """
    current_user = get_current_user(credentials)
    
    caller_user = get_current_user(credentials)
    caller_id = caller_user["user_db"]["id"]
    # Delegate permission logic to service
    return users_service.get_all_for_caller(caller_id, active_only)

@router.get("/ext-id/{ext_id}", response_model=UsersRead)
def get_user_by_ext_id(
    ext_id: str = Path(..., description="External ID (Keycloak sub) of the user"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Returns a user by their external ID (Keycloak sub).
    """
    current_user = get_current_user(credentials)
    caller_id = current_user["user_db"]["id"]
    user = users_service.get_by_ext_id(ext_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    # Visibility: allow if caller is superadmin, admin (but not if target is superadmin), or the user themself
    if str(user.id) == str(caller_id):
        return user
    if is_superadmin(caller_id):
        return user
    if is_admin(caller_id):
        # admins cannot view superadmins
        if is_superadmin(str(user.id)):
            raise HTTPException(status_code=404, detail="User not found")
        return user
    raise HTTPException(status_code=403, detail="Not authorized to view this user")

@router.get("/name/{name}", response_model=List[UsersRead])
def get_users_by_name(
    name: str = Path(..., description="First name or last name substring to search for"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Returns users whose first_name or last_name contains the given substring (case-insensitive).
    """
    current_user = get_current_user(credentials)
    caller_id = current_user["user_db"]["id"]
    # delegate permission & efficient filtering to service
    return users_service.get_by_name_for_caller(name, caller_id)

@router.put("/{user_id}/activate", response_model=UsersRead)
def activate_user(
    user_id: str = Path(..., description="Unique identifier of the user to activate"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Activates a user account.
    """
    current_user = get_current_user(credentials)
    updater_user_id = current_user["user_db"]["id"]
    return users_service.activate_user(user_id, updater_user_id)

@router.put("/{user_id}/deactivate", response_model=UsersRead)
def deactivate_user(
    user_id: str = Path(..., description="Unique identifier of the user to deactivate"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Deactivates a user account.
    """
    current_user = get_current_user(credentials)
    updater_user_id = current_user["user_db"]["id"]
    return users_service.deactivate_user(user_id, updater_user_id)

@router.get("/{user_id}", response_model=UsersRead)
def get_user_by_id(
    user_id: str = Path(..., description="Unique identifier of the user"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Returns a user by its ID.
    """
    current_user = get_current_user(credentials)
    caller_id = current_user["user_db"]["id"]
    # allow if caller is the same user
    if str(user_id) == str(caller_id):
        return users_service.get_by_id(user_id)
    # allow superadmin
    if is_superadmin(caller_id):
        return users_service.get_by_id(user_id)
    # allow admin except when target is superadmin
    if is_admin(caller_id):
        if is_superadmin(user_id):
            raise HTTPException(status_code=404, detail="User not found")
        return users_service.get_by_id(user_id)
    raise HTTPException(status_code=403, detail="Not authorized to view this user")
