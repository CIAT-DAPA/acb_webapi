from typing import List, Any, Optional
from bson import ObjectId
from fastapi import HTTPException
from acb_orm.collections.bulletins_version import BulletinsVersion
from acb_orm.schemas.bulletins_version_schema import BulletinsVersionCreate, BulletinsVersionUpdate, BulletinsVersionRead
from mongoengine import Document, DoesNotExist
from auth.access_utils import serialize_log
from tools.logger import logger
from tools.utils import parse_object_ids
from .base_service import BaseService

class BulletinsVersionService(
    BaseService[
        BulletinsVersion,
        BulletinsVersionCreate,
        BulletinsVersionRead,
        BulletinsVersionUpdate
    ]
):
    @staticmethod
    def _serialize_document(document) -> dict:
        data = document.to_mongo().to_dict()
        if '_id' in data:
            data['id'] = str(data['_id'])
        if 'bulletin_master_id' in data and isinstance(data['bulletin_master_id'], ObjectId):
            data['bulletin_master_id'] = str(data['bulletin_master_id'])
        if 'previous_version_id' in data and isinstance(data['previous_version_id'], ObjectId):
            data['previous_version_id'] = str(data['previous_version_id'])
        if 'log' in data:
            data['log'] = serialize_log(document.log)
        return data

    def __init__(self):
        super().__init__(BulletinsVersion, BulletinsVersionRead)

    def get_by_master_id(self, bulletin_master_id: str) -> List[BulletinsVersionRead]:
        objs = self.model.objects(bulletin_master_id=bulletin_master_id).order_by('-log__created_at')
        return [self.read_schema.model_validate(self._serialize_document(obj)) for obj in objs]

    def clone_version(self, version: BulletinsVersionRead, new_bulletin_master_id: str, user_id: str):
        version_data = version.model_dump()
        version_data.pop("id", None)
        version_data["bulletin_master_id"] = new_bulletin_master_id
        version_data["previous_version_id"] = None
        new_version = self.create(BulletinsVersionCreate(**version_data), user_id)
        return new_version
