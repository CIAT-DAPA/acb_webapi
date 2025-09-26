from typing import List, Optional, Any
from bson import ObjectId
from fastapi import HTTPException
from acb_orm.collections.groups import Group
from acb_orm.schemas.groups_schema import GroupsCreate, GroupsRead, GroupsUpdate
from mongoengine import DoesNotExist
from auth.access_utils import serialize_log
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

    def add_user_to_group(self, group_id: str, user_id: str, role_id: str) -> GroupsRead:
        """
        Agrega un usuario con un rol al grupo especificado.
        Si el usuario ya existe en el grupo, lanza un error.
        """
        group = Group.objects.get(id=group_id)
        if any(str(ua.user_id.id) == str(user_id) for ua in group.users_access):
            raise HTTPException(status_code=400, detail="El usuario ya pertenece al grupo")
        group.users_access.append({"user_id": ObjectId(user_id), "role_id": ObjectId(role_id)})
        group.save()
        return self.read_schema.model_validate(self._serialize_document(group))

    def remove_user_from_group(self, group_id: str, user_id: str) -> GroupsRead:
        """
        Elimina un usuario del grupo especificado.
        Si el usuario no está en el grupo, lanza un error.
        """
        group = Group.objects.get(id=group_id)
        original_count = len(group.users_access)
        group.users_access = [ua for ua in group.users_access if str(ua.user_id.id) != str(user_id)]
        if len(group.users_access) == original_count:
            raise HTTPException(status_code=404, detail="El usuario no pertenece al grupo")
        group.save()
        return self.read_schema.model_validate(self._serialize_document(group))

    def update_user_role_in_group(self, group_id: str, user_id: str, new_role_id: str) -> GroupsRead:
        """
        Actualiza el rol de un usuario en el grupo especificado.
        Si el usuario no está en el grupo, lanza un error.
        """
        group = Group.objects.get(id=group_id)
        updated = False
        for ua in group.users_access:
            if str(ua.user_id.id) == str(user_id):
                ua.role_id = ObjectId(new_role_id)
                updated = True
        if not updated:
            raise HTTPException(status_code=404, detail="El usuario no pertenece al grupo")
        group.save()
        return self.read_schema.model_validate(self._serialize_document(group))

    def list_users_in_group(self, group_id: str) -> list:
        """
        Devuelve la lista de usuarios (y sus roles) de un grupo dado.
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
        Devuelve todos los grupos a los que pertenece un usuario y el rol que tiene en cada uno.
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
        Verifica si el usuario tiene el rol especificado en el grupo.
        """
        group = Group.objects.get(id=group_id)
        for ua in group.users_access:
            if str(ua.user_id.id) == str(user_id) and str(ua.role_id.id) == str(role_id):
                return True
        return False
