from datetime import datetime
from typing import Any, List, Optional

from bson import ObjectId
from fastapi import HTTPException
from mongoengine import DoesNotExist, Document

from acb_orm.collections.bulletins_master import BulletinsMaster
from acb_orm.enums.status_bulletin import StatusBulletin
from acb_orm.schemas.bulletins_master_schema import (
    BulletinsMasterCreate,
    BulletinsMasterRead,
    BulletinsMasterUpdate,
)
from auth.access_utils import serialize_log
from tools.logger import logger

from .base_service import BaseService
from .bulletins_version_service import BulletinsVersionService


class BulletinsMasterService(
    BaseService[
        BulletinsMaster,
        BulletinsMasterCreate,
        BulletinsMasterRead,
        BulletinsMasterUpdate,
    ]
):
    @staticmethod
    def _serialize_document(document) -> dict:
        data = document.to_mongo().to_dict()
        if "_id" in data:
            data["id"] = str(data["_id"])
        if "current_version_id" in data and isinstance(
            data["current_version_id"], ObjectId
        ):
            data["current_version_id"] = str(data["current_version_id"])
        if "base_template_master_id" in data and isinstance(
            data["base_template_master_id"], ObjectId
        ):
            data["base_template_master_id"] = str(data["base_template_master_id"])
        if "base_template_version_id" in data and isinstance(
            data["base_template_version_id"], ObjectId
        ):
            data["base_template_version_id"] = str(data["base_template_version_id"])
        if "log" in data:
            data["log"] = serialize_log(document.log)
        if "access_config" in data and isinstance(data["access_config"], dict):
            if "allowed_groups" in data["access_config"] and isinstance(
                data["access_config"]["allowed_groups"], list
            ):
                data["access_config"]["allowed_groups"] = [
                    str(group_id)
                    for group_id in data["access_config"]["allowed_groups"]
                ]
        return data

    def __init__(self):
        super().__init__(BulletinsMaster, BulletinsMasterRead)

    def get_by_name(self, name: str) -> List[BulletinsMasterRead]:
        objs = BulletinsMaster.objects(bulletin_name__icontains=name)
        return [
            BulletinsMasterRead.model_validate(self._serialize_document(obj))
            for obj in objs
        ]

    def get_by_status(self, status: str) -> List[BulletinsMasterRead]:
        if status not in StatusBulletin._value2member_map_:
            raise ValueError(
                f"Invalid status: {status}. "
                f"Allowed: {list(StatusBulletin._value2member_map_.keys())}"
            )
        objs = BulletinsMaster.objects(status=status)
        return [
            BulletinsMasterRead.model_validate(self._serialize_document(obj))
            for obj in objs
        ]

    def _get_by_field(self, field: str, value: Any) -> List[BulletinsMasterRead]:
        objs = BulletinsMaster.objects(**{field: value})
        return [
            BulletinsMasterRead.model_validate(self._serialize_document(obj))
            for obj in objs
        ]

    def get_current_version_id(self, bulletin_master_id: str) -> Any:
        if not ObjectId.is_valid(bulletin_master_id):
            logger.error(f"Invalid bulletin ID format: {bulletin_master_id}")
            raise HTTPException(status_code=400, detail="Invalid bulletin ID format")
        try:
            obj = BulletinsMaster.objects(id=bulletin_master_id).first()
            if not obj:
                raise HTTPException(status_code=404, detail="Bulletin master not found")
            return obj.current_version_id
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(f"Error in get_current_version_id: {exc}")
            raise HTTPException(
                status_code=500,
                detail=f"Internal error: {str(exc)}",
            ) from exc

    def transition_status_atomically(
        self,
        bulletin_master_id: str,
        expected_status: StatusBulletin,
        target_status: StatusBulletin,
        user_id: str,
    ) -> BulletinsMasterRead:
        """Change status only if the stored status still matches expected_status.

        This prevents two reviewers from approving/rejecting the same bulletin at
        nearly the same time. It is implemented locally and does not require any
        change to acb_orm.
        """
        if not ObjectId.is_valid(bulletin_master_id):
            raise HTTPException(status_code=400, detail="Invalid bulletin ID format")
        if not ObjectId.is_valid(user_id):
            raise HTTPException(status_code=400, detail="Invalid user ID format")

        bulletin_object_id = ObjectId(bulletin_master_id)
        now = datetime.now()

        updated = BulletinsMaster.objects(
            id=bulletin_object_id,
            status=expected_status,
        ).modify(
            new=True,
            set__status=target_status,
            set__log__updater_user_id=ObjectId(user_id),
            set__log__updated_at=now,
        )

        if updated is None:
            current = BulletinsMaster.objects(id=bulletin_object_id).first()
            if current is None:
                raise HTTPException(status_code=404, detail="Bulletin not found")

            current_status = getattr(current.status, "value", str(current.status))
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "BULLETIN_STATUS_CHANGED",
                    "message": (
                        "The bulletin status changed before this action could "
                        "be completed."
                    ),
                    "expected_status": expected_status.value,
                    "current_status": current_status,
                },
            )

        return BulletinsMasterRead.model_validate(self._serialize_document(updated))

    def clone_master_with_version(
        self,
        bulletin_master: BulletinsMasterRead,
        user_id: str,
        bulletin_name: Optional[str] = None,
        description: Optional[str] = None,
    ):
        master_data = bulletin_master.model_dump()
        master_data.pop("id", None)
        master_data["bulletin_name"] = (
            bulletin_name or master_data["bulletin_name"] + " (clon)"
        )
        master_data["status"] = StatusBulletin.DRAFT
        if description:
            master_data["description"] = description
        master_data["current_version_id"] = None

        new_master = self.create(BulletinsMasterCreate(**master_data), user_id)
        version_service = BulletinsVersionService()
        current_version_id = bulletin_master.current_version_id
        if current_version_id:
            current_version = version_service.get_by_id(str(current_version_id))
            cloned_version = version_service.clone_version(
                current_version,
                new_master.id,
                user_id,
            )
            new_master = self.update(
                str(new_master.id),
                BulletinsMasterUpdate(current_version_id=cloned_version.id),
                user_id,
            )
        else:
            cloned_version = None
        return new_master, cloned_version