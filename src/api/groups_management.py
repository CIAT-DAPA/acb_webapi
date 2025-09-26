from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from services.groups_service import GroupsService
from acb_orm.schemas.groups_schema import GroupsRead, GroupsCreate, GroupsUpdate
from auth.access_utils import get_current_user

router = APIRouter(prefix="/groups", tags=["Groups"], include_in_schema=False)
groups_service = GroupsService()

@router.get("/", response_model=List[GroupsRead])
def list_groups(user=Depends(get_current_user)):
    return groups_service.get_all()

@router.get("/by-country/{country_code}", response_model=List[GroupsRead])
def get_groups_by_country(country_code: str, user=Depends(get_current_user)):
    return groups_service.get_groups_by_country(country_code)

@router.get("/by-user/{user_id}", response_model=List[GroupsRead])
def get_groups_by_user(user_id: str, user=Depends(get_current_user)):
    return groups_service.get_groups_by_user_id(user_id)

@router.get("/{group_id}", response_model=GroupsRead)
def get_group_by_id(group_id: str, user=Depends(get_current_user)):
    return groups_service.get_by_id(group_id)

@router.post("/", response_model=GroupsRead)
def create_group(group: GroupsCreate, user=Depends(get_current_user)):
    return groups_service.create(group)

@router.put("/{group_id}", response_model=GroupsRead)
def update_group(group_id: str, group: GroupsUpdate, user=Depends(get_current_user)):
    return groups_service.update(group_id, group)

@router.delete("/{group_id}")
def delete_group(group_id: str, user=Depends(get_current_user)):
    groups_service.delete(group_id)
    return {"detail": "Group deleted"}

# --- Servicios avanzados ---

@router.post("/{group_id}/add-user")
def add_user_to_group(group_id: str, user_id: str, role_id: str, user=Depends(get_current_user)):
    return groups_service.add_user_to_group(group_id, user_id, role_id)

@router.post("/{group_id}/remove-user")
def remove_user_from_group(group_id: str, user_id: str, user=Depends(get_current_user)):
    return groups_service.remove_user_from_group(group_id, user_id)

@router.post("/{group_id}/update-user-role")
def update_user_role_in_group(group_id: str, user_id: str, new_role_id: str, user=Depends(get_current_user)):
    return groups_service.update_user_role_in_group(group_id, user_id, new_role_id)

@router.get("/{group_id}/users")
def list_users_in_group(group_id: str, user=Depends(get_current_user)):
    return groups_service.list_users_in_group(group_id)

@router.get("/user/{user_id}/groups-roles")
def list_groups_and_roles_for_user(user_id: str, user=Depends(get_current_user)):
    return groups_service.list_groups_and_roles_for_user(user_id)

@router.get("/{group_id}/user/{user_id}/has-role/{role_id}")
def user_has_role_in_group(group_id: str, user_id: str, role_id: str, user=Depends(get_current_user)):
    return {"has_role": groups_service.user_has_role_in_group(group_id, user_id, role_id)}
