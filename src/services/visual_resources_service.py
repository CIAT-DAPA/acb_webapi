from typing import List, Any, Optional, Dict
from bson import ObjectId
from fastapi import HTTPException
from acb_orm.collections.visual_resources import VisualResources
from acb_orm.schemas.visual_resources_schema import VisualResourcesCreate, VisualResourcesUpdate, VisualResourcesRead
from acb_orm.enums.status_visual_resource import StatusVisualResource
from acb_orm.enums.file_type import FileType
from mongoengine import Document, DoesNotExist
from auth.access_utils import (
    serialize_log,
    is_superadmin,
    user_has_permission,
    user_has_permission_in_any_group,
)
from constants.permissions import (
    MODULE_TEMPLATE_MANAGEMENT,
    MODULE_CARD_MANAGEMENT,
)
from tools.logger import logger
from tools.utils import parse_object_ids
from .base_service import BaseService

VISUAL_RESOURCE_PERMISSION_MODULES = (
    MODULE_TEMPLATE_MANAGEMENT,
    MODULE_CARD_MANAGEMENT,
)

class VisualResourcesService(
    BaseService[
        VisualResources,
        VisualResourcesCreate,
        VisualResourcesRead,
        VisualResourcesUpdate
    ]
):
    @staticmethod
    def _serialize_document(document) -> dict:
        data = document.to_mongo().to_dict()
        if '_id' in data:
            data['id'] = str(data['_id'])
        if 'log' in data:
            data['log'] = serialize_log(document.log)
        if 'access_config' in data and isinstance(data['access_config'], dict):
            if 'allowed_groups' in data['access_config'] and isinstance(data['access_config']['allowed_groups'], list):
                data['access_config']['allowed_groups'] = [str(g) for g in data['access_config']['allowed_groups']]
        return data

    def __init__(self):
        super().__init__(VisualResources, VisualResourcesRead)

    def get_by_name(self, name: str) -> List[VisualResourcesRead]:
        objs = VisualResources.objects(file_name__icontains=name)
        return [VisualResourcesRead.model_validate(self._serialize_document(obj)) for obj in objs]

    def get_by_status(self, status: str) -> List[VisualResourcesRead]:
        if status not in StatusVisualResource._value2member_map_:
            raise ValueError(f"Invalid status: {status}. Allowed: {list(StatusVisualResource._value2member_map_.keys())}")
        objs = VisualResources.objects(status=status)
        return [VisualResourcesRead.model_validate(self._serialize_document(obj)) for obj in objs]

    def get_by_file_type(self, file_type: str) -> List[VisualResourcesRead]:
        if file_type not in FileType._value2member_map_:
            raise ValueError(f"Invalid file type: {file_type}. Allowed: {list(FileType._value2member_map_.keys())}")
        objs = VisualResources.objects(file_type=file_type)
        return [VisualResourcesRead.model_validate(self._serialize_document(obj)) for obj in objs]

    @staticmethod
    def _access_type_value(access_config: Any) -> str:
        if isinstance(access_config, dict):
            value = access_config.get("access_type")
        else:
            value = getattr(access_config, "access_type", None)
        return getattr(value, "value", value) or "public"

    @staticmethod
    def _allowed_group_ids(access_config: Any) -> List[str]:
        if isinstance(access_config, dict):
            groups = access_config.get("allowed_groups") or []
        else:
            groups = getattr(access_config, "allowed_groups", None) or []
        return [str(getattr(group, "id", group)) for group in groups]

    @staticmethod
    def _has_permission_in_group(
        user_id: str,
        group_id: str,
        action: str,
    ) -> bool:
        return any(
            user_has_permission(user_id, group_id, module, action)
            for module in VISUAL_RESOURCE_PERMISSION_MODULES
        )

    @staticmethod
    def _has_permission_in_any_group(
        user_id: str,
        action: str,
    ) -> bool:
        return any(
            user_has_permission_in_any_group(user_id, module, action)
            for module in VISUAL_RESOURCE_PERMISSION_MODULES
        )

    def _require_access_config_permission(
        self,
        user_id: str,
        access_config: Any,
        action: str,
    ) -> None:
        if is_superadmin(user_id):
            return

        access_type = self._access_type_value(access_config)
        allowed_groups = self._allowed_group_ids(access_config)

        if access_type == "public":
            if not self._has_permission_in_any_group(user_id, action):
                raise HTTPException(
                    status_code=403,
                    detail=(
                        f"User needs {MODULE_TEMPLATE_MANAGEMENT}.{action} "
                        f"or {MODULE_CARD_MANAGEMENT}.{action} permission"
                    ),
                )
            return

        if not allowed_groups:
            raise HTTPException(
                status_code=403,
                detail="Visual resource has no authorized groups",
            )

        # For writes, the user must be allowed to manage the resource in every
        # group to which the resource is assigned. Permission can come from
        # either Templates or Cards in each group.
        for group_id in allowed_groups:
            if not self._has_permission_in_group(user_id, group_id, action):
                raise HTTPException(
                    status_code=403,
                    detail=(
                        f"User needs {MODULE_TEMPLATE_MANAGEMENT}.{action} "
                        f"or {MODULE_CARD_MANAGEMENT}.{action} permission "
                        f"in group {group_id}"
                    ),
                )

    def get_accessible_resources_with_permission(
    self,
    user_id: str,
    filters: Optional[Dict[str, Any]] = None,
) -> List[VisualResourcesRead]:
        """
        Return resources readable by any authenticated user.

        Public resources are visible to everyone authenticated.
        Restricted resources remain limited to users that belong
        to one of the resource's allowed groups.

        No Templates/Cards read permission is required.
        """
        return self.get_accessible_resources(
            user_id,
            filters,
        )

    def create_with_permission(
        self,
        resource: VisualResourcesCreate,
        user_id: str,
    ) -> VisualResourcesRead:
        self._require_access_config_permission(
            user_id,
            resource.access_config,
            "c",
        )
        return super().create(resource, user_id, module=None)

    def update_with_permission(
        self,
        resource_id: str,
        resource: VisualResourcesUpdate,
        user_id: str,
        action: str = "u",
    ) -> VisualResourcesRead:
        try:
            current = VisualResources.objects.get(id=resource_id)
        except DoesNotExist:
            raise HTTPException(status_code=404, detail="Resource not found")

        self._require_access_config_permission(
            user_id,
            current.access_config,
            action,
        )

        # If access scope changes, the user must also have permission in the
        # destination scope. Merge partial AccessConfigUpdate values with the
        # current configuration before checking permissions.
        if resource.access_config is not None:
            next_access_type = (
                resource.access_config.access_type
                if resource.access_config.access_type is not None
                else current.access_config.access_type
            )
            next_allowed_groups = (
                resource.access_config.allowed_groups
                if resource.access_config.allowed_groups is not None
                else current.access_config.allowed_groups
            )
            self._require_access_config_permission(
                user_id,
                {
                    "access_type": next_access_type,
                    "allowed_groups": next_allowed_groups,
                },
                action,
            )

        return super().update(resource_id, resource, user_id, module=None)
