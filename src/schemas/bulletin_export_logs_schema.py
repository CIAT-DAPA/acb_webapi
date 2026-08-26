from datetime import datetime
from typing import List, Optional

from acb_orm.enums.export_format import ExportFormat
from acb_orm.schemas.bulletin_export_log_schema import BulletinExportLogRead
from pydantic import BaseModel, ConfigDict, Field


class BulletinExportLogRegisterRequest(BaseModel):
    """Body used to register an export that was just performed.

    The user is always taken from the access token, never from the body, so the
    audit trail cannot be attributed to someone else.
    """

    bulletin_master_id: str = Field(
        ...,
        description="ObjectId of the exported bulletin master.",
    )
    bulletin_version_id: Optional[str] = Field(
        None,
        description=(
            "ObjectId of the exported version. "
            "Defaults to the bulletin's current version."
        ),
    )
    format: ExportFormat = Field(
        ...,
        description="Format in which the bulletin was exported.",
    )
    bulletin_title: Optional[str] = Field(
        None,
        description=(
            "Title at the moment of the export. "
            "Defaults to the current bulletin name."
        ),
    )
    exported_at: Optional[datetime] = Field(
        None,
        description="Moment of the export. Defaults to the server time.",
    )

    model_config = ConfigDict(from_attributes=True)


class BulletinExportLogPage(BaseModel):
    """Paginated audit listing of bulletin exports."""

    total: int = Field(..., description="Total number of matching export logs.")
    limit: int = Field(..., description="Maximum number of records per page.")
    skip: int = Field(..., description="Number of skipped records.")
    page: int = Field(..., description="Current page number.")
    total_pages: int = Field(..., description="Total number of pages.")
    has_next: bool = Field(..., description="Indicates if there is a next page.")
    results: List[BulletinExportLogRead] = Field(
        ...,
        description="Export logs for the current page, newest first.",
    )


class ExportCount(BaseModel):
    """One row of an export counter breakdown."""

    key: str = Field(..., description="Grouping key (format value or user ID).")
    label: Optional[str] = Field(
        None,
        description="Human friendly label for the key.",
    )
    total: int = Field(..., description="Number of exports for this key.")


class BulletinExportLogStats(BaseModel):
    """Aggregated export counters for the audit dashboard."""

    total: int = Field(..., description="Total number of exports.")
    by_format: List[ExportCount] = Field(
        default_factory=list,
        description="Export count per format.",
    )
    by_user: List[ExportCount] = Field(
        default_factory=list,
        description="Export count per user, most active first.",
    )
    first_export_at: Optional[datetime] = Field(
        None,
        description="Timestamp of the oldest matching export.",
    )
    last_export_at: Optional[datetime] = Field(
        None,
        description="Timestamp of the most recent matching export.",
    )
