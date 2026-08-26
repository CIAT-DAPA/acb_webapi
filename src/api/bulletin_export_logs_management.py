from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from acb_orm.enums.export_format import ExportFormat
from acb_orm.schemas.bulletin_export_log_schema import BulletinExportLogRead

from auth.access_utils import (
    get_current_user,
    is_admin,
    is_superadmin,
    user_has_permission,
)
from constants.permissions import (
    ACTION_READ,
    MODULE_BULLETINS_COMPOSER,
    MODULE_DASHBOARD_BULLETINS,
)
from schemas.bulletin_export_logs_schema import (
    BulletinExportLogPage,
    BulletinExportLogRegisterRequest,
    BulletinExportLogStats,
)
from services.bulletin_export_log_service import BulletinExportLogService
from services.bulletins_master_service import BulletinsMasterService

router = APIRouter(
    prefix="/bulletin-export-logs",
    tags=["Bulletin Export Logs"],
)
export_logs_service = BulletinExportLogService()
bulletins_master_service = BulletinsMasterService()
security = HTTPBearer()

FORMATS = list(ExportFormat._value2member_map_.keys())


def get_bulletin_groups(bulletin) -> List[str]:
    """
    Return the group IDs associated with the bulletin.
    """
    access_config = getattr(bulletin, "access_config", None)
    allowed_groups = getattr(access_config, "allowed_groups", []) or []
    return [
        str(group.id) if hasattr(group, "id") else str(group)
        for group in allowed_groups
    ]


def get_accessible_bulletin_or_404(user_id: str, bulletin_master_id: str):
    """
    Return the bulletin master if the user can see it, 404 otherwise.
    """
    bulletins = bulletins_master_service.get_accessible_resources(
        user_id,
        filters={"id": bulletin_master_id},
    )
    if not bulletins:
        raise HTTPException(status_code=404, detail="Bulletin not found or no access")
    return bulletins[0]


def can_audit_bulletin_exports(user_id: str, bulletin) -> bool:
    """
    Return True when the user may read the export history of a bulletin.

    Reading the audit trail is a dashboard capability, so it is granted to
    superadmins and to users with DASHBOARD_BULLETINS read permission in at
    least one of the bulletin's groups.
    """
    if is_superadmin(user_id):
        return True
    return any(
        user_has_permission(
            user_id,
            group_id,
            MODULE_DASHBOARD_BULLETINS,
            ACTION_READ,
        )
        for group_id in get_bulletin_groups(bulletin)
    )


def require_bulletin_audit_access(user_id: str, bulletin_master_id: str):
    """
    Raise 403 when the user cannot read the export history of the bulletin.
    """
    bulletin = get_accessible_bulletin_or_404(user_id, bulletin_master_id)
    if not can_audit_bulletin_exports(user_id, bulletin):
        raise HTTPException(
            status_code=403,
            detail=(
                "User does not have permission to read the export history "
                "of this bulletin."
            ),
        )
    return bulletin


def require_global_audit_access(user_id: str) -> None:
    """
    Raise 403 when the user cannot read the export history across bulletins.

    Cross-bulletin auditing is not scoped to a single group, so it is limited
    to superadmins and group admins.
    """
    if is_superadmin(user_id) or is_admin(user_id):
        return
    raise HTTPException(
        status_code=403,
        detail=(
            "User does not have permission to read the global export history. "
            "Filter by bulletin_master_id instead."
        ),
    )


def require_export_permission(user_id: str, bulletin) -> None:
    """
    Raise 403 when the user is not allowed to export the bulletin.

    Exporting is a read over the bulletin content, so having access to the
    bulletin plus read permission in the composer or dashboard module in one of
    its groups is enough.
    """
    if is_superadmin(user_id):
        return
    bulletin_groups = get_bulletin_groups(bulletin)
    for group_id in bulletin_groups:
        for module in (MODULE_BULLETINS_COMPOSER, MODULE_DASHBOARD_BULLETINS):
            if user_has_permission(user_id, group_id, module, ACTION_READ):
                return
    if not bulletin_groups:
        # Boletín público: cualquier usuario autenticado que lo pueda ver
        # también puede exportarlo, así que solo se registra la auditoría.
        return
    raise HTTPException(
        status_code=403,
        detail="User does not have permission to export this bulletin.",
    )


# --- Write ---

@router.post("/", response_model=BulletinExportLogRead)
def register_bulletin_export(
    export: BulletinExportLogRegisterRequest = Body(...),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """
    Register an export performed by the current user on a bulletin.

    The user is taken from the token. If `bulletin_version_id` is omitted the
    bulletin's current version is used, and if `bulletin_title` is omitted the
    current bulletin name is stored so the log survives later renames.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]

    bulletin = get_accessible_bulletin_or_404(user_id, export.bulletin_master_id)
    require_export_permission(user_id, bulletin)

    return export_logs_service.register_export(
        user_id=user_id,
        bulletin_master_id=export.bulletin_master_id,
        export_format=export.format,
        bulletin_version_id=export.bulletin_version_id,
        bulletin_title=export.bulletin_title,
        exported_at=export.exported_at,
    )


# --- Read ---

@router.get("/", response_model=BulletinExportLogPage)
def list_bulletin_export_logs(
    bulletin_master_id: Optional[str] = Query(
        None,
        description="Filter by bulletin master ID",
    ),
    bulletin_version_id: Optional[str] = Query(
        None,
        description="Filter by exported bulletin version ID",
    ),
    user_id: Optional[str] = Query(
        None,
        description="Filter by the user who performed the export",
    ),
    format: Optional[str] = Query(
        None,
        description=f"Filter by export format. Possible options: {FORMATS}",
    ),
    date_from: Optional[datetime] = Query(
        None,
        description="Only exports performed at or after this date (ISO 8601)",
    ),
    date_to: Optional[datetime] = Query(
        None,
        description="Only exports performed at or before this date (ISO 8601)",
    ),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=200, description="Records per page"),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """
    Paginated export audit trail, newest export first.

    When `bulletin_master_id` is provided the caller needs dashboard read
    permission in one of that bulletin's groups; without it the listing spans
    every bulletin and is restricted to superadmins and group admins.
    """
    user = get_current_user(credentials)
    current_user_id = user["user_db"]["id"]

    if bulletin_master_id:
        require_bulletin_audit_access(current_user_id, bulletin_master_id)
    else:
        require_global_audit_access(current_user_id)

    filters = export_logs_service.build_filters(
        user_id=user_id,
        bulletin_master_id=bulletin_master_id,
        bulletin_version_id=bulletin_version_id,
        export_format=format,
        date_from=date_from,
        date_to=date_to,
    )
    return export_logs_service.get_paginated(filters, page=page, limit=limit)


@router.get("/me", response_model=BulletinExportLogPage)
def list_my_bulletin_exports(
    bulletin_master_id: Optional[str] = Query(
        None,
        description="Filter by bulletin master ID",
    ),
    format: Optional[str] = Query(
        None,
        description=f"Filter by export format. Possible options: {FORMATS}",
    ),
    date_from: Optional[datetime] = Query(
        None,
        description="Only exports performed at or after this date (ISO 8601)",
    ),
    date_to: Optional[datetime] = Query(
        None,
        description="Only exports performed at or before this date (ISO 8601)",
    ),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=200, description="Records per page"),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """
    Exports performed by the current user. Needs no extra permission.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]

    filters = export_logs_service.build_filters(
        user_id=user_id,
        bulletin_master_id=bulletin_master_id,
        export_format=format,
        date_from=date_from,
        date_to=date_to,
    )
    return export_logs_service.get_paginated(filters, page=page, limit=limit)


@router.get("/stats", response_model=BulletinExportLogStats, include_in_schema=False)
def get_bulletin_export_stats(
    bulletin_master_id: Optional[str] = Query(
        None,
        description="Restrict the counters to a single bulletin",
    ),
    format: Optional[str] = Query(
        None,
        description=f"Restrict the counters to one format. Options: {FORMATS}",
    ),
    date_from: Optional[datetime] = Query(
        None,
        description="Only exports performed at or after this date (ISO 8601)",
    ),
    date_to: Optional[datetime] = Query(
        None,
        description="Only exports performed at or before this date (ISO 8601)",
    ),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """
    Export counters by format and by user, for the audit dashboard.

    Same permissions as the listing: bulletin scoped for group members with
    dashboard read permission, global for superadmins and group admins.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]

    if bulletin_master_id:
        require_bulletin_audit_access(user_id, bulletin_master_id)
    else:
        require_global_audit_access(user_id)

    filters = export_logs_service.build_filters(
        bulletin_master_id=bulletin_master_id,
        export_format=format,
        date_from=date_from,
        date_to=date_to,
    )
    return export_logs_service.get_stats(filters)


@router.get("/bulletin/{bulletin_master_id}", response_model=List[BulletinExportLogRead])
def get_export_logs_by_bulletin(
    bulletin_master_id: str = Path(..., description="Bulletin master ID"),
    limit: Optional[int] = Query(
        None,
        ge=1,
        le=1000,
        description="Maximum number of records to return",
    ),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """
    Full export history of one bulletin, newest export first.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]

    require_bulletin_audit_access(user_id, bulletin_master_id)

    filters = export_logs_service.build_filters(
        bulletin_master_id=bulletin_master_id,
    )
    return export_logs_service.get_by_filters(filters, limit=limit)


@router.get("/user/{user_id}", response_model=List[BulletinExportLogRead])
def get_export_logs_by_user(
    user_id: str = Path(..., description="ID of the user who performed the exports"),
    limit: Optional[int] = Query(
        None,
        ge=1,
        le=1000,
        description="Maximum number of records to return",
    ),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """
    Export history of one user. Users may always read their own history.
    """
    user = get_current_user(credentials)
    current_user_id = user["user_db"]["id"]

    if str(user_id) != str(current_user_id):
        require_global_audit_access(current_user_id)

    filters = export_logs_service.build_filters(user_id=user_id)
    return export_logs_service.get_by_filters(filters, limit=limit)


@router.get("/{export_log_id}", response_model=BulletinExportLogRead)
def get_export_log_by_id(
    export_log_id: str = Path(..., description="ID of the export log record"),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """
    Return a single export log entry.

    Visible to its own author, and to anyone allowed to audit the exports of
    the referenced bulletin.
    """
    user = get_current_user(credentials)
    current_user_id = user["user_db"]["id"]

    export_log = export_logs_service.get_by_id(export_log_id)
    if str(export_log.user_id) != str(current_user_id):
        require_bulletin_audit_access(current_user_id, export_log.bulletin_master_id)
    return export_log
