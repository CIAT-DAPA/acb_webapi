from typing import List, Any, Optional
from bson import ObjectId
from fastapi import HTTPException
from acb_orm.collections.visual_resources import VisualResources
from acb_orm.schemas.visual_resources_schema import VisualResourcesCreate, VisualResourcesUpdate, VisualResourcesRead
from acb_orm.enums.status_visual_resource import StatusVisualResource
from acb_orm.enums.file_type import FileType
from mongoengine import Document, DoesNotExist
from auth.access_utils import serialize_log
from tools.logger import logger
from tools.utils import parse_object_ids
from .base_service import BaseService

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

