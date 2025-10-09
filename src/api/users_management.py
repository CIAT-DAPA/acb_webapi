from fastapi import APIRouter, HTTPException, Depends, Path, Query
from typing import List, Optional
from services.users_service import UsersService
from acb_orm.schemas.users_schema import UsersCreate, UsersUpdate, UsersRead
from auth.access_utils import get_current_user
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
    Creates a new user document.
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
    Updates a user document by its ID. Updates the log with current user info.
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
    Returns all users. Can filter by active status using query parameter.
    """
    current_user = get_current_user(credentials)
    
    if active_only is True:
        return users_service.get_active_users()
    elif active_only is False:
        return users_service.get_inactive_users()
    else:
        return users_service.get_all()

@router.get("/ext-id/{ext_id}", response_model=UsersRead)
def get_user_by_ext_id(
    ext_id: str = Path(..., description="External ID (Keycloak sub) of the user"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Returns a user by their external ID (Keycloak sub).
    """
    current_user = get_current_user(credentials)
    user = users_service.get_by_ext_id(ext_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.get("/name/{name}", response_model=List[UsersRead])
def get_users_by_name(
    name: str = Path(..., description="First name or last name substring to search for"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Returns users whose first_name or last_name contains the given substring (case-insensitive).
    """
    current_user = get_current_user(credentials)
    return users_service.get_by_name(name)

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
    return users_service.get_by_id(user_id)
