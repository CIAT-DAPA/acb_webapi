from typing import List, Optional
from bson import ObjectId
from fastapi import HTTPException
from acb_orm.collections.roles import Role
from acb_orm.schemas.roles_schema import RolesCreate, RolesRead, RolesUpdate
from mongoengine import DoesNotExist
from auth.access_utils import serialize_log, is_superadmin
from .base_service import BaseService

class RoleService(
    BaseService[
        Role,
        RolesCreate,
        RolesRead,
        RolesUpdate
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
        super().__init__(Role, RolesRead)

    def get_by_name(self, name: str) -> List[RolesRead]:
        objs = Role.objects(role_name__icontains=name)
        return [self.read_schema.model_validate(self._serialize_document(obj)) for obj in objs]

    def get_by_id(self, id: str) -> RolesRead:
        try:
            obj = Role.objects.get(id=id)
            return self.read_schema.model_validate(self._serialize_document(obj))
        except DoesNotExist:
            raise HTTPException(status_code=404, detail="Role not found")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")

    def get_all(self, filters: Optional[dict] = None) -> List[RolesRead]:
        # If caller passes a user_id via filters, respect it for visibility of 'superadmin'
        user_id = None
        if filters and 'user_id' in filters:
            user_id = filters.pop('user_id')

        objs = Role.objects(**(filters or {}))

        result = []
        for obj in objs:
            if obj.role_name == 'superadmin' and not (user_id and is_superadmin(user_id)):
                # skip superadmin role for non-superadmin users
                continue
            result.append(self.read_schema.model_validate(self._serialize_document(obj)))
        return result

    # Métodos create, update y delete ya están cubiertos por BaseService
