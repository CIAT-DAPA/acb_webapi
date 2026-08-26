from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from fastapi import HTTPException
from mongoengine import ValidationError as MongoValidationError

from acb_orm.collections.bulletin_export_log import BulletinExportLog
from acb_orm.collections.bulletins_master import BulletinsMaster
from acb_orm.collections.bulletins_version import BulletinsVersion
from acb_orm.collections.users import User
from acb_orm.enums.export_format import ExportFormat
from acb_orm.schemas.bulletin_export_log_schema import (
    BulletinExportLogCreate,
    BulletinExportLogRead,
    BulletinExportLogUpdate,
)

from tools.logger import logger

from .base_service import BaseService


class BulletinExportLogService(
    BaseService[
        BulletinExportLog,
        BulletinExportLogCreate,
        BulletinExportLogRead,
        BulletinExportLogUpdate,
    ]
):
    """Audit trail for every export performed on a bulletin version.

    Export logs are append-only: the service exposes a single write path
    (`register_export`) plus read/aggregation helpers. Rewriting history is
    intentionally not offered here.
    """

    @staticmethod
    def _serialize_document(document) -> dict:
        data = document.to_mongo().to_dict()
        if "_id" in data:
            data["id"] = str(data["_id"])
        for field in ("user_id", "bulletin_master_id", "bulletin_version_id"):
            if field in data and isinstance(data[field], ObjectId):
                data[field] = str(data[field])

        # La auditoría se consulta por usuario, así que se resuelve el nombre
        # igual que en el resto de los servicios: sin dereferenciar el
        # ReferenceField, que rompería si el usuario ya no existe.
        data["user_first_name"] = None
        data["user_last_name"] = None
        user_id = data.get("user_id")
        if user_id:
            try:
                user = User.objects(id=user_id).first()
                if user:
                    data["user_first_name"] = user.first_name
                    data["user_last_name"] = user.last_name
            except Exception as exc:
                logger.warning(f"Could not fetch user details for {user_id}: {exc}")
        return data

    def __init__(self):
        super().__init__(BulletinExportLog, BulletinExportLogRead)

    # --- Write path ---

    def register_export(
        self,
        user_id: str,
        bulletin_master_id: str,
        export_format: ExportFormat,
        bulletin_version_id: Optional[str] = None,
        bulletin_title: Optional[str] = None,
        exported_at: Optional[datetime] = None,
    ) -> BulletinExportLogRead:
        """Record one export action.

        `bulletin_version_id` defaults to the bulletin's current version and
        `bulletin_title` to the bulletin name at this moment, so the log keeps
        the title even if the bulletin is renamed later.
        """
        if not ObjectId.is_valid(user_id):
            raise HTTPException(status_code=400, detail="Invalid user ID format")
        if not ObjectId.is_valid(bulletin_master_id):
            raise HTTPException(
                status_code=400,
                detail="Invalid bulletin master ID format",
            )

        bulletin = BulletinsMaster.objects(id=bulletin_master_id).first()
        if not bulletin:
            raise HTTPException(status_code=404, detail="Bulletin master not found")

        version = self._resolve_version(bulletin, bulletin_version_id)

        try:
            export_log = BulletinExportLog(
                user_id=ObjectId(user_id),
                bulletin_master_id=bulletin.id,
                bulletin_version_id=version.id,
                bulletin_title=bulletin_title or bulletin.bulletin_name,
                format=ExportFormat(export_format),
                exported_at=exported_at or datetime.now(),
            )
            export_log.save()
        except MongoValidationError as exc:
            logger.error(f"Validation error in register_export: {exc}")
            raise HTTPException(
                status_code=400,
                detail=f"Validation error: {str(exc)}",
            ) from exc
        except Exception as exc:
            logger.error(f"Error in register_export: {exc}")
            raise HTTPException(
                status_code=500,
                detail=f"Error registering bulletin export: {str(exc)}",
            ) from exc

        logger.info(
            f"Export registered: bulletin={bulletin.id} version={version.id} "
            f"user={user_id} format={export_log.format.value}"
        )
        return self.read_schema.model_validate(self._serialize_document(export_log))

    def create(
        self,
        obj_in: BulletinExportLogCreate,
        user_id: Optional[str] = None,
        module: Optional[str] = None,
    ) -> BulletinExportLogRead:
        """Create from the ORM schema, reusing the `register_export` path.

        `user_id`/`module` from the base signature are ignored: this collection
        has neither access_config nor log, and the acting user always travels
        inside `obj_in.user_id`.
        """
        return self.register_export(
            user_id=obj_in.user_id,
            bulletin_master_id=obj_in.bulletin_master_id,
            export_format=obj_in.format,
            bulletin_version_id=obj_in.bulletin_version_id,
            bulletin_title=obj_in.bulletin_title,
            exported_at=obj_in.exported_at,
        )

    def _resolve_version(
        self,
        bulletin: BulletinsMaster,
        bulletin_version_id: Optional[str],
    ) -> BulletinsVersion:
        """Return the exported version, defaulting to the current one."""
        if bulletin_version_id:
            if not ObjectId.is_valid(bulletin_version_id):
                raise HTTPException(
                    status_code=400,
                    detail="Invalid bulletin version ID format",
                )
            version = BulletinsVersion.objects(id=bulletin_version_id).first()
            if not version:
                raise HTTPException(
                    status_code=404,
                    detail="Bulletin version not found",
                )
            master_ref = version.bulletin_master_id
            master_id = getattr(master_ref, "id", master_ref)
            if str(master_id) != str(bulletin.id):
                raise HTTPException(
                    status_code=400,
                    detail="The version does not belong to the given bulletin",
                )
            return version

        current_version_ref = bulletin.current_version_id
        if not current_version_ref:
            raise HTTPException(
                status_code=400,
                detail=(
                    "The bulletin has no current version; "
                    "bulletin_version_id is required"
                ),
            )
        current_version_id = getattr(
            current_version_ref,
            "id",
            current_version_ref,
        )
        version = BulletinsVersion.objects(id=current_version_id).first()
        if not version:
            raise HTTPException(
                status_code=404,
                detail="Bulletin current version not found",
            )
        return version

    # --- Read path ---

    def build_filters(
        self,
        user_id: Optional[str] = None,
        bulletin_master_id: Optional[str] = None,
        bulletin_version_id: Optional[str] = None,
        export_format: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Translate the query params of the audit endpoints into ORM filters."""
        filters: Dict[str, Any] = {}

        for field, value in (
            ("user_id", user_id),
            ("bulletin_master_id", bulletin_master_id),
            ("bulletin_version_id", bulletin_version_id),
        ):
            if value:
                if not ObjectId.is_valid(value):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid {field} format: {value}",
                    )
                filters[field] = ObjectId(value)

        if export_format:
            if export_format not in ExportFormat._value2member_map_:
                allowed = list(ExportFormat._value2member_map_.keys())
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid format: {export_format}. Allowed: {allowed}",
                )
            filters["format"] = export_format

        if date_from:
            filters["exported_at__gte"] = date_from
        if date_to:
            filters["exported_at__lte"] = date_to

        return filters

    def get_paginated(
        self,
        filters: Optional[Dict[str, Any]] = None,
        page: int = 1,
        limit: int = 20,
        order_by: str = "-exported_at",
    ) -> Dict[str, Any]:
        """Paginated audit listing, newest export first by default."""
        page = max(page, 1)
        limit = max(min(limit, 200), 1)
        try:
            query = self.model.objects(**(filters or {})).order_by(order_by)
            total = query.count()
            skip = (page - 1) * limit
            results = [
                self.read_schema.model_validate(self._serialize_document(obj))
                for obj in query.skip(skip).limit(limit)
            ]
            total_pages = (total + limit - 1) // limit
            return {
                "total": total,
                "limit": limit,
                "skip": skip,
                "page": page,
                "total_pages": total_pages,
                "has_next": (skip + limit) < total,
                "results": results,
            }
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(f"Error in get_paginated: {exc}")
            raise HTTPException(
                status_code=500,
                detail=f"Internal error: {str(exc)}",
            ) from exc

    def get_by_filters(
        self,
        filters: Optional[Dict[str, Any]] = None,
        order_by: str = "-exported_at",
        limit: Optional[int] = None,
    ) -> List[BulletinExportLogRead]:
        """Non paginated listing, used by the bulletin/user shortcuts."""
        try:
            query = self.model.objects(**(filters or {})).order_by(order_by)
            if limit:
                query = query.limit(limit)
            return [
                self.read_schema.model_validate(self._serialize_document(obj))
                for obj in query
            ]
        except Exception as exc:
            logger.error(f"Error in get_by_filters: {exc}")
            raise HTTPException(
                status_code=500,
                detail=f"Internal error: {str(exc)}",
            ) from exc

    def get_by_id(self, id: str) -> BulletinExportLogRead:
        if not ObjectId.is_valid(id):
            raise HTTPException(
                status_code=400,
                detail="Invalid export log ID format",
            )
        return super().get_by_id(id)

    def get_stats(self, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Aggregated counters for the audit dashboard.

        Returns the total number of exports, the breakdown by format and by
        user (with names resolved), and the first/last export timestamps.
        """
        try:
            query = self.model.objects(**(filters or {}))
            total = query.count()

            by_format = [
                {
                    "key": str(row["_id"]),
                    "label": str(row["_id"]).upper() if row["_id"] else None,
                    "total": row["total"],
                }
                for row in query.aggregate([
                    {"$group": {"_id": "$format", "total": {"$sum": 1}}},
                    {"$sort": {"total": -1, "_id": 1}},
                ])
            ]

            by_user = []
            for row in query.aggregate([
                {"$group": {"_id": "$user_id", "total": {"$sum": 1}}},
                {"$sort": {"total": -1}},
            ]):
                user = User.objects(id=row["_id"]).first() if row["_id"] else None
                full_name = (
                    " ".join(
                        part for part in (user.first_name, user.last_name) if part
                    ).strip()
                    if user
                    else None
                )
                by_user.append({
                    "key": str(row["_id"]),
                    "label": full_name or None,
                    "total": row["total"],
                })

            first_log = query.order_by("exported_at").first()
            last_log = query.order_by("-exported_at").first()

            return {
                "total": total,
                "by_format": by_format,
                "by_user": by_user,
                "first_export_at": first_log.exported_at if first_log else None,
                "last_export_at": last_log.exported_at if last_log else None,
            }
        except Exception as exc:
            logger.error(f"Error in get_stats: {exc}")
            raise HTTPException(
                status_code=500,
                detail=f"Internal error: {str(exc)}",
            ) from exc
