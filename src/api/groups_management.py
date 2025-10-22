from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from services.groups_service import GroupsService
from acb_orm.schemas.groups_schema import GroupsRead, GroupsCreate, GroupsUpdate
from auth.access_utils import get_current_user, user_has_permission, is_superadmin, user_is_group_admin
from constants.permissions import MODULE_ACCESS_CONTROL, ACTION_CREATE, ACTION_UPDATE, ACTION_DELETE

router = APIRouter(prefix="/groups", tags=["Groups"])
groups_service = GroupsService()

@router.get("/", response_model=List[GroupsRead])
def list_groups(user=Depends(get_current_user), include_users: Optional[bool] = Query(False)):
    user_id = user["user_db"]["id"]
    # superadmins can see all groups
    if is_superadmin(user_id):
        return groups_service.get_all(include_users=include_users)
    # otherwise return only groups where the user belongs
    return groups_service.get_groups_by_user_id(user_id, include_users=include_users)

@router.get("/by-country/{country_code}", response_model=List[GroupsRead])
def get_groups_by_country(country_code: str, user=Depends(get_current_user), include_users: Optional[bool] = Query(False)):
    user_id = user["user_db"]["id"]
    # show only groups in that country where the user is a member, unless superadmin
    if is_superadmin(user_id):
        return groups_service.get_groups_by_country(country_code, include_users=include_users)
    # filter user's groups by country
    user_groups = groups_service.get_groups_by_user_id(user_id, include_users=include_users)
    return [g for g in user_groups if g.country and g.country.lower() == country_code.lower()]

@router.get("/by-user/{user_id}", response_model=List[GroupsRead])
def get_groups_by_user(user_id: str, user=Depends(get_current_user), include_users: Optional[bool] = Query(False)):
    requester_id = user["user_db"]["id"]
    if requester_id == user_id or is_superadmin(requester_id):
        return groups_service.get_groups_by_user_id(user_id, include_users=include_users)
    raise HTTPException(status_code=403, detail="Not authorized to view other user's groups")

@router.get("/{group_id}", response_model=GroupsRead)
def get_group_by_id(group_id: str, user=Depends(get_current_user), include_users: Optional[bool] = Query(False)):
    user_id = user["user_db"]["id"]
    if is_superadmin(user_id):
        group = groups_service.get_by_id(group_id, include_users=include_users)
        return group
    # check membership
    groups = groups_service.get_groups_by_user_id(user_id, include_users=include_users)
    if any(str(g.id) == str(group_id) for g in groups):
        group = groups_service.get_by_id(group_id, include_users=include_users)
        return group
    raise HTTPException(status_code=403, detail="Not authorized to view this group")

@router.post("/", response_model=GroupsRead)
def create_group(group: GroupsCreate, user=Depends(get_current_user)):
    user_id = user["user_db"]["id"]
    if not is_superadmin(user_id):
        raise HTTPException(status_code=403, detail="Only superadmins can create groups")
    return groups_service.create(group, user_id)

@router.put("/{group_id}", response_model=GroupsRead)
def update_group(group_id: str, group: GroupsUpdate, user=Depends(get_current_user)):
    user_id = user["user_db"]["id"]
    # allow update if superadmin or has update permission in access_control or is group admin
    if is_superadmin(user_id) or user_has_permission(user_id, group_id, MODULE_ACCESS_CONTROL, ACTION_UPDATE) or user_is_group_admin(user_id, group_id):
        return groups_service.update(group_id, group, user_id)
    raise HTTPException(status_code=403, detail="Not authorized to update this group")

# --- Servicios avanzados ---

@router.post("/{group_id}/add-user")
def add_user_to_group(group_id: str, user_id: str, role_id: str, user=Depends(get_current_user)):
    updater_user_id = user["user_db"]["id"]
    if not (is_superadmin(updater_user_id) or user_has_permission(updater_user_id, group_id, MODULE_ACCESS_CONTROL, ACTION_CREATE) or user_is_group_admin(updater_user_id, group_id)):
        raise HTTPException(status_code=403, detail="Not authorized to add users to this group")
    return groups_service.add_user_to_group(group_id, user_id, role_id, updater_user_id)

@router.post("/{group_id}/remove-user")
def remove_user_from_group(group_id: str, user_id: str, user=Depends(get_current_user)):
    updater_user_id = user["user_db"]["id"]
    if not (is_superadmin(updater_user_id) or user_has_permission(updater_user_id, group_id, MODULE_ACCESS_CONTROL, ACTION_DELETE) or user_is_group_admin(updater_user_id, group_id)):
        raise HTTPException(status_code=403, detail="Not authorized to remove users from this group")
    return groups_service.remove_user_from_group(group_id, user_id, updater_user_id)

@router.post("/{group_id}/update-user-role")
def update_user_role_in_group(group_id: str, user_id: str, new_role_id: str, user=Depends(get_current_user)):
    updater_user_id = user["user_db"]["id"]
    if not (is_superadmin(updater_user_id) or user_has_permission(updater_user_id, group_id, MODULE_ACCESS_CONTROL, ACTION_UPDATE) or user_is_group_admin(updater_user_id, group_id)):
        raise HTTPException(status_code=403, detail="Not authorized to change roles in this group")
    return groups_service.update_user_role_in_group(group_id, user_id, new_role_id, updater_user_id)

@router.get("/{group_id}/users")
def list_users_in_group(group_id: str, user=Depends(get_current_user)):
    user_id = user["user_db"]["id"]
    if is_superadmin(user_id):
        return groups_service.list_users_in_group(group_id)
    # only group members can list users
    groups = groups_service.get_groups_by_user_id(user_id)
    if any(str(g.id) == str(group_id) for g in groups):
        return groups_service.list_users_in_group(group_id)
    raise HTTPException(status_code=403, detail="Not authorized to view group members")

@router.get("/user/{user_id}/groups-roles")
def list_groups_and_roles_for_user(user_id: str, user=Depends(get_current_user)):
    requester_id = user["user_db"]["id"]
    if requester_id == user_id or is_superadmin(requester_id):
        return groups_service.list_groups_and_roles_for_user(user_id)
    raise HTTPException(status_code=403, detail="Not authorized to view this user's groups and roles")

@router.get("/{group_id}/user/{user_id}/has-role/{role_id}")
def user_has_role_in_group(group_id: str, user_id: str, role_id: str, user=Depends(get_current_user)):
    requester_id = user["user_db"]["id"]
    if is_superadmin(requester_id):
        return {"has_role": groups_service.user_has_role_in_group(group_id, user_id, role_id)}
    # allow if requester is member of the group
    groups = groups_service.get_groups_by_user_id(requester_id)
    if any(str(g.id) == str(group_id) for g in groups):
        return {"has_role": groups_service.user_has_role_in_group(group_id, user_id, role_id)}
    raise HTTPException(status_code=403, detail="Not authorized to view role membership")
