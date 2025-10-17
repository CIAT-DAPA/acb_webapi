from typing import List, Optional, Any
from bson import ObjectId
from fastapi import HTTPException
from acb_orm.collections.groups import Group
from acb_orm.collections.roles import Role
from acb_orm.auxiliaries.user_access import UserAccess
from acb_orm.schemas.groups_schema import GroupsCreate, GroupsRead, GroupsUpdate
from acb_orm.schemas.log_schema import LogUpdate
from mongoengine import DoesNotExist
from auth.access_utils import serialize_log, user_has_permission, is_superadmin, user_is_group_admin
from constants.permissions import MODULE_ACCESS_CONTROL, ACTION_CREATE, ACTION_UPDATE, ACTION_DELETE
from .base_service import BaseService

class GroupsService(
    BaseService[
        Group,
        GroupsCreate,
        GroupsRead,
        GroupsUpdate
    ]
):
    @staticmethod
    def _serialize_document(document) -> dict:
        data = document.to_mongo().to_dict()
        if '_id' in data:
            data['id'] = str(data['_id'])
        if 'log' in data:
            data['log'] = serialize_log(document.log)
        if 'users_access' in data and isinstance(document.users_access, list):
            data['users_access'] = [
            {
                "user_id": str(ua.user_id.id) if ua.user_id else None,
                "role_id": str(ua.role_id.id) if ua.role_id else None
            }
            for ua in document.users_access
            ]
        return data

    def __init__(self):
        super().__init__(Group, GroupsRead)

    def create(self, obj_in: GroupsCreate, user_id: Optional[str] = None, module: Optional[str] = None) -> GroupsRead:
        """Only superadmin can create groups."""
        if not (user_id and is_superadmin(user_id)):
            raise HTTPException(status_code=403, detail="Only superadmins can create groups")
        # call base create but pass module for consistency
        return super().create(obj_in, user_id, module="group_management")

    def update(self, id: str, obj_in: GroupsUpdate, user_id: Optional[str] = None, module: Optional[str] = None) -> GroupsRead:
        """Allow update if superadmin or group admin or has access_control.u permission."""
        if not user_id:
            raise HTTPException(status_code=403, detail="User id required for update")
        if is_superadmin(user_id) or user_has_permission(user_id, id, MODULE_ACCESS_CONTROL, ACTION_UPDATE) or user_is_group_admin(user_id, id):
            # use base update to handle log management
            return super().update(id, obj_in, user_id, module="group_management")
        raise HTTPException(status_code=403, detail="Not authorized to update this group")

    def get_by_name(self, name: str) -> List[GroupsRead]:
        objs = Group.objects(group_name__icontains=name)
        return [self.read_schema.model_validate(self._serialize_document(obj)) for obj in objs]

    def get_by_id(self, id: str) -> GroupsRead:
        try:
            obj = Group.objects.get(id=id)
            return self.read_schema.model_validate(self._serialize_document(obj))
        except DoesNotExist:
            raise HTTPException(status_code=404, detail="Group not found")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")

    def get_all(self, filters: Optional[dict] = None) -> List[GroupsRead]:
        objs = Group.objects(**(filters or {}))
        return [self.read_schema.model_validate(self._serialize_document(obj)) for obj in objs]
    
    def get_groups_by_user_id(self, user_id: str) -> List[GroupsRead]:
        """
        Returns all groups where the given user_id is present in users_access.
        """
        objs = Group.objects(users_access__user_id=ObjectId(user_id))
        return [self.read_schema.model_validate(self._serialize_document(obj)) for obj in objs]
    
    def get_groups_by_country(self, country_code: str) -> List[GroupsRead]:
        """
        Returns all groups whose 'country' field matches the provided ISO 2 code (case-insensitive).
        """
        objs = Group.objects(country__iexact=country_code)
        return [self.read_schema.model_validate(self._serialize_document(obj)) for obj in objs]

    def _update_group_log(self, group: Group, user_id: Optional[str] = None) -> None:
        """
        Updates the log of a group when modifications are made.
        If user_id is provided, updates the log with the updater information.
        """
        if user_id is not None and hasattr(group, 'log') and group.log:
            # Preserve original creator information
            original_log = group.to_mongo().to_dict().get('log', {})
            print(original_log)
            log_update = LogUpdate(updater_user_id=user_id).model_dump()
            if original_log:
                log_update["creator_user_id"] = original_log.get("creator_user_id")
                log_update["created_at"] = original_log.get("created_at")
            # Update the log fields
            for key, value in log_update.items():
                if isinstance(value, str) and ObjectId.is_valid(value):
                    value = ObjectId(value)
                setattr(group.log, key, value)

    def add_user_to_group(self, group_id: str, user_id: str, role_id: str, updater_user_id: Optional[str] = None) -> GroupsRead:
        """
        Adds a user with a role to the specified group.
        If the user already exists in the group, raises an error.
        """
        # Authorization: only superadmin or group admin or user with create permission can add
        if not (updater_user_id and (is_superadmin(updater_user_id) or user_has_permission(updater_user_id, group_id, MODULE_ACCESS_CONTROL, ACTION_CREATE) or user_is_group_admin(updater_user_id, group_id))):
            raise HTTPException(status_code=403, detail="Not authorized to add users to this group")

        try:
            group = Group.objects.get(id=group_id)
        except Group.DoesNotExist:
            raise HTTPException(status_code=404, detail="Group not found")

        # check role exists
        role_obj = Role.objects(id=role_id).first()
        if not role_obj:
            raise HTTPException(status_code=404, detail="Role not found")

        # prevent assigning superadmin by non-superadmin
        if role_obj.role_name in [r for r in ["superadmin"]] and not is_superadmin(updater_user_id):
            raise HTTPException(status_code=403, detail="Only superadmin can assign superadmin role")

        if any(str(ua.user_id.id) == str(user_id) for ua in group.users_access):
            raise HTTPException(status_code=400, detail="User already belongs to the group")

        user_access = UserAccess(user_id=ObjectId(user_id), role_id=role_obj)
        group.users_access.append(user_access)
        self._update_group_log(group, updater_user_id)
        group.save()
        return self.read_schema.model_validate(self._serialize_document(group))

    def remove_user_from_group(self, group_id: str, user_id: str, updater_user_id: Optional[str] = None) -> GroupsRead:
        """
        Removes a user from the specified group.
        If the user is not in the group, raises an error.
        """
        # Authorization: only superadmin or group admin or user with delete permission can remove
        if not (updater_user_id and (is_superadmin(updater_user_id) or user_has_permission(updater_user_id, group_id, MODULE_ACCESS_CONTROL, ACTION_DELETE) or user_is_group_admin(updater_user_id, group_id))):
            raise HTTPException(status_code=403, detail="Not authorized to remove users from this group")

        group = Group.objects.get(id=group_id)
        original_count = len(group.users_access)
        group.users_access = [ua for ua in group.users_access if str(ua.user_id.id) != str(user_id)]
        if len(group.users_access) == original_count:
            raise HTTPException(status_code=404, detail="User does not belong to the group")
        self._update_group_log(group, updater_user_id)
        group.save()
        return self.read_schema.model_validate(self._serialize_document(group))

    def update_user_role_in_group(self, group_id: str, user_id: str, new_role_id: str, updater_user_id: Optional[str] = None) -> GroupsRead:
        """
        Updates a user's role in the specified group.
        If the user is not in the group, raises an error.
        """
        # Authorization: only superadmin or group admin or user with update permission can change roles
        if not (updater_user_id and (is_superadmin(updater_user_id) or user_has_permission(updater_user_id, group_id, MODULE_ACCESS_CONTROL, ACTION_UPDATE) or user_is_group_admin(updater_user_id, group_id))):
            raise HTTPException(status_code=403, detail="Not authorized to change roles in this group")

        try:
            group = Group.objects.get(id=group_id)
        except Group.DoesNotExist:
            raise HTTPException(status_code=404, detail="Group not found")

        try:
            new_role = Role.objects.get(id=new_role_id)
        except Role.DoesNotExist:
            raise HTTPException(status_code=404, detail="Role not found")

        # prevent assigning superadmin by non-superadmin
        if new_role.role_name == 'superadmin' and not is_superadmin(updater_user_id):
            raise HTTPException(status_code=403, detail="Only superadmin can assign superadmin role")

        updated = False
        for ua in group.users_access:
            if str(ua.user_id.id) == str(user_id):
                ua.role_id = new_role
                updated = True
        if not updated:
            raise HTTPException(status_code=404, detail="User does not belong to the group")
        self._update_group_log(group, updater_user_id)
        group.save()
        return self.read_schema.model_validate(self._serialize_document(group))

    def list_users_in_group(self, group_id: str) -> list:
        """
        Returns the list of users (and their roles) for a given group.
        """
        group = Group.objects.get(id=group_id)
        return [
            {
                "user_id": str(ua.user_id.id),
                "role_id": str(ua.role_id.id)
            }
            for ua in group.users_access
        ]

    def list_groups_and_roles_for_user(self, user_id: str) -> list:
        """
        Returns all groups a user belongs to and their role in each one.
        """
        groups = Group.objects(users_access__user_id=ObjectId(user_id))
        result = []
        for group in groups:
            for ua in group.users_access:
                if str(ua.user_id.id) == str(user_id):
                    result.append({
                        "group_id": str(group.id),
                        "group_name": group.group_name,
                        "role_id": str(ua.role_id.id)
                    })
        return result

    def user_has_role_in_group(self, group_id: str, user_id: str, role_id: str) -> bool:
        """
        Verifies if the user has the specified role in the group.
        """
        group = Group.objects.get(id=group_id)
        for ua in group.users_access:
            if str(ua.user_id.id) == str(user_id) and str(ua.role_id.id) == str(role_id):
                return True
        return False
