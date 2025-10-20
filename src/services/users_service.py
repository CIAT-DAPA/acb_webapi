from typing import List, Any, Optional
from bson import ObjectId
from fastapi import HTTPException
from acb_orm.collections.users import User
from acb_orm.schemas.users_schema import UsersCreate, UsersUpdate, UsersRead
from mongoengine.queryset.visitor import Q
from mongoengine import Document, DoesNotExist
from auth.access_utils import serialize_log
from auth.access_utils import is_superadmin, is_admin, get_superadmins
from tools.logger import logger
from tools.utils import parse_object_ids
from .base_service import BaseService

class UsersService(
    BaseService[
        User,
        UsersCreate,
        UsersRead,
        UsersUpdate
    ]
):
    @staticmethod
    def _serialize_document(document) -> dict:
        data = document.to_mongo().to_dict()
        if '_id' in data:
            data['id'] = str(data['_id'])
        if 'log' in data:
            data['log'] = serialize_log(document.log)
        return data

    def __init__(self):
        super().__init__(User, UsersRead)

    def get_by_ext_id(self, ext_id: str) -> Optional[UsersRead]:
        """
        Returns a user by their external ID (Keycloak sub).
        """
        obj = User.objects(ext_id=ext_id).first()
        if not obj:
            return None
        return self.read_schema.model_validate(self._serialize_document(obj))

    def get_by_name(self, name: str) -> List[UsersRead]:
        """
        Returns users whose first_name or last_name contains the given substring (case-insensitive).
        """
        objs = User.objects(Q(first_name__icontains=name) | Q(last_name__icontains=name))
        return [self.read_schema.model_validate(self._serialize_document(obj)) for obj in objs]

    def get_by_name_for_caller(self, name: str, caller_user_id: str) -> List[UsersRead]:
        """
        Returns users matching name but filtered according to caller permissions.

        - superadmin: returns all matching users
        - admin: returns matches excluding users who are superadmins
        - non-admin: raises HTTPException(403)
        Implementation uses an ID-only query first to avoid loading full documents when many matches exist.
        """
        # Superadmin shortcut
        if is_superadmin(caller_user_id):
            objs = User.objects(Q(first_name__icontains=name) | Q(last_name__icontains=name))
            return [self.read_schema.model_validate(self._serialize_document(obj)) for obj in objs]

        # Admin: we need to exclude superadmins
        if is_admin(caller_user_id):
            try:
                # 1) get matching ids (lightweight)
                id_qs = User.objects(Q(first_name__icontains=name) | Q(last_name__icontains=name)).only('id')
                matching_ids = [str(d.id) for d in id_qs]

                if not matching_ids:
                    return []

                # 2) get superadmin ids using helper
                super_users = get_superadmins()
                super_ids = {str(u.id) for u in super_users}

                # 3) subtract and fetch final users
                filtered_ids = [ObjectId(i) for i in matching_ids if i not in super_ids]
                if not filtered_ids:
                    return []

                objs = User.objects(id__in=filtered_ids)
                return [self.read_schema.model_validate(self._serialize_document(obj)) for obj in objs]

            except Exception as e:
                logger.exception("Error filtering users by name for caller: %s", e)
                raise HTTPException(status_code=500, detail="Internal error while searching users")

        # Non-admins are not allowed
        raise HTTPException(status_code=403, detail="Not authorized to search users")

    def get_active_users(self) -> List[UsersRead]:
        """
        Returns all active users.
        """
        objs = User.objects(is_active=True)
        return [self.read_schema.model_validate(self._serialize_document(obj)) for obj in objs]

    def get_all_for_caller(self, caller_user_id: str, active_only: Optional[bool] = None) -> List[UsersRead]:
        """
        Returns users depending on caller permissions.

        - superadmin: returns all users (optionally filter by active_only)
        - admin: returns all users except those who have the 'superadmin' role
        - non-admin: raises HTTPException(403)
        """
        # Validate flags
        query = {}
        if active_only is True:
            query['is_active'] = True
        elif active_only is False:
            query['is_active'] = False

        # Superadmin sees everything
        if is_superadmin(caller_user_id):
            objs = User.objects(**query)
            return [self.read_schema.model_validate(self._serialize_document(obj)) for obj in objs]

        # Admin sees everyone except users that have role 'superadmin'
        if is_admin(caller_user_id):
            # get all users and filter out those who are superadmins
            objs = User.objects(**query)
            result = []
            for obj in objs:
                # Determine if this user is a superadmin by checking groups
                try:
                    # use access_utils.is_superadmin which inspects groups
                    if is_superadmin(str(obj.id)):
                        continue
                except Exception:
                    # on error, be conservative and include the user
                    pass
                result.append(self.read_schema.model_validate(self._serialize_document(obj)))
            return result

        # Non-admins are not allowed to list users
        raise HTTPException(status_code=403, detail="Not authorized to list users")

    def get_inactive_users(self) -> List[UsersRead]:
        """
        Returns all inactive users.
        """
        objs = User.objects(is_active=False)
        return [self.read_schema.model_validate(self._serialize_document(obj)) for obj in objs]

    def activate_user(self, user_id: str, updater_user_id: str) -> UsersRead:
        """
        Activates a user account.
        """
        update_data = UsersUpdate(is_active=True)
        return self.update(user_id, update_data, updater_user_id)

    def deactivate_user(self, user_id: str, updater_user_id: str) -> UsersRead:
        """
        Deactivates a user account.
        """
        update_data = UsersUpdate(is_active=False)
        return self.update(user_id, update_data, updater_user_id)
