from typing import List, Any, Optional
from bson import ObjectId
from fastapi import HTTPException
from acb_orm.collections.users import User
from acb_orm.schemas.users_schema import UsersCreate, UsersUpdate, UsersRead
from mongoengine import Document, DoesNotExist
from auth.access_utils import serialize_log
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
        from mongoengine.queryset.visitor import Q
        objs = User.objects(Q(first_name__icontains=name) | Q(last_name__icontains=name))
        return [self.read_schema.model_validate(self._serialize_document(obj)) for obj in objs]

    def get_active_users(self) -> List[UsersRead]:
        """
        Returns all active users.
        """
        objs = User.objects(is_active=True)
        return [self.read_schema.model_validate(self._serialize_document(obj)) for obj in objs]

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
