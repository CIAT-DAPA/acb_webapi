from typing import List, Optional, Dict, Any
from bson import ObjectId
from fastapi import HTTPException
from acb_orm.collections.roles import Role
from acb_orm.schemas.roles_schema import RolesCreate, RolesRead, RolesUpdate
from mongoengine import DoesNotExist
from auth.access_utils import serialize_log, is_superadmin
from .base_service import BaseService


class RoleService(BaseService[Role, RolesCreate, RolesRead, RolesUpdate]):
    @staticmethod
    def _serialize_document(document) -> dict:
        data = document.to_mongo().to_dict()
        if "_id" in data:
            data["id"] = str(data["_id"])
        if "log" in data:
            data["log"] = serialize_log(document.log)
        return data

    def __init__(self):
        super().__init__(Role, RolesRead)

    def get_by_name(self, name: str) -> List[RolesRead]:
        objs = Role.objects(role_name__icontains=name)
        return [
            self.read_schema.model_validate(self._serialize_document(obj))
            for obj in objs
        ]

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
        if filters and "user_id" in filters:
            user_id = filters.pop("user_id")

        objs = Role.objects(**(filters or {}))

        result = []
        for obj in objs:
            if obj.role_name == "superadmin" and not (
                user_id and is_superadmin(user_id)
            ):
                # skip superadmin role for non-superadmin users
                continue
            result.append(
                self.read_schema.model_validate(self._serialize_document(obj))
            )
        return result

    @staticmethod
    def role_matches_rule(role: Role, rule: Dict[str, Any]) -> bool:
        """
        Evaluates whether a Role matches a single permission rule.
        rule = {
            "module": str,
            "actions": List[str],
            "require_all": bool,               # default True
            "exclude_if_module": Optional[str],
            "exclude_if_actions": Optional[List[str]],
        }
        """
        module = rule["module"]
        actions = rule["actions"]
        require_all = rule.get("require_all", True)

        perms = role.permissions.get(module, {})
        has_required = (
            all(perms.get(a, False) for a in actions)
            if require_all
            else any(perms.get(a, False) for a in actions)
        )
        if not has_required:
            return False

        exclude_module = rule.get("exclude_if_module")
        exclude_actions = rule.get("exclude_if_actions")
        if exclude_module and exclude_actions:
            exclude_perms = role.permissions.get(exclude_module, {})
            if any(exclude_perms.get(a, False) for a in exclude_actions):
                return False

        return True

    @staticmethod
    def role_matches_rules(
        role: Role,
        rules: List[Dict[str, Any]],
        match_mode: str = "any",
    ) -> bool:
        """
        Evaluates a list of rules against a Role.
        match_mode: "any" (matches at least one) | "all" (must match all)
        """
        results = [RoleService.role_matches_rule(role, rule) for rule in rules]
        return any(results) if match_mode == "any" else all(results)

    def get_roles_map(self, role_ids: List[str]) -> Dict[str, Role]:
        """
        Bulk fetch roles by ID, returned as {role_id: Role}.
        Useful for evaluating permissions across multiple roles at once.
        """
        if not role_ids:
            return {}
        roles = Role.objects(id__in=[ObjectId(r) for r in role_ids])
        return {str(r.id): r for r in roles}

    # create, update, and delete methods are already covered by BaseService
