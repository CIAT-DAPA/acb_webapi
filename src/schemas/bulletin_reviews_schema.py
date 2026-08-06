from datetime import datetime
from typing import List, Literal, Optional

from acb_orm.schemas.comment_schema import TargetElementSchema
from acb_orm.schemas.log_schema import LogRead
from pydantic import BaseModel, ConfigDict, Field


class TargetElementRead(BaseModel):
    """Schema for target element in comments (local, used by CommentRead)."""

    section_id: Optional[str] = None
    block_id: Optional[str] = None
    field_id: Optional[str] = None


class CommentRead(BaseModel):
    """Schema for reading comments with expanded author info."""

    comment_id: str
    parent_comment_id: Optional[str] = None
    comment_path: str
    bulletin_version_id: str
    text: str
    author_id: str
    author_first_name: Optional[str] = None
    author_last_name: Optional[str] = None
    created_at: datetime
    target_element: Optional[TargetElementRead] = None
    replies: List["CommentRead"] = Field(default_factory=list)
    is_editable: bool = True

    model_config = ConfigDict(from_attributes=True)


class CommentCreateRequest(BaseModel):
    """Schema for creating a comment via API request."""

    text: str = Field(..., min_length=1)
    target_element: Optional[TargetElementSchema] = None
    parent_comment_id: Optional[str] = None


class CommentUpdateRequest(BaseModel):
    """Schema for updating a comment's text. Only the author can edit."""

    text: str = Field(..., min_length=1)


class CommentCreateResponse(BaseModel):
    """Schema for the response after creating a comment."""

    comment_id: str
    parent_comment_id: Optional[str] = None
    comment_path: str
    bulletin_version_id: str
    text: str
    author_id: str
    author_first_name: Optional[str] = None
    author_last_name: Optional[str] = None
    created_at: datetime
    target_element: Optional[TargetElementRead] = None
    is_editable: bool = True


class ReviewCycleRead(BaseModel):
    """Schema for reading review cycles."""

    cycle_number: int
    bulletin_version_id: str
    submitted_at: datetime
    completed_at: Optional[datetime] = None
    outcome: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class BulletinReviewRead(BaseModel):
    """Schema for reading bulletin review with all cycles and comments."""

    id: str
    bulletin_master_id: str
    reviewer_user_id: Optional[str] = None
    reviewer_first_name: Optional[str] = None
    reviewer_last_name: Optional[str] = None
    review_cycles: List[ReviewCycleRead] = Field(default_factory=list)
    comments: List[CommentRead] = Field(default_factory=list)
    log: LogRead

    model_config = ConfigDict(from_attributes=True)


class ReviewSessionCreateRequest(BaseModel):
    """Starts or refreshes the presence session for one browser tab."""

    session_id: str = Field(
        ...,
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )


class ReviewDecisionRequest(BaseModel):
    """Confirmation payload for approve/reject while other reviewers are active."""

    confirm_other_reviewers: bool = False


class ActiveReviewerRead(BaseModel):
    user_id: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    entered_at: datetime
    last_seen_at: datetime
    session_count: int = 1
    is_current_user: bool = False


class ReviewSessionRead(BaseModel):
    session_id: str
    bulletin_id: str
    user_id: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    entered_at: datetime
    last_seen_at: datetime


class ReviewDecisionRead(BaseModel):
    cycle_number: int
    action: Literal["approved", "rejected"]
    target_status: str
    decided_by: str
    decided_by_first_name: Optional[str] = None
    decided_by_last_name: Optional[str] = None
    decided_at: datetime


class ReviewCollaborationStateRead(BaseModel):
    bulletin_id: str
    status: str
    cycle_number: Optional[int] = None
    active_reviewers: List[ActiveReviewerRead] = Field(default_factory=list)
    final_decision: Optional[ReviewDecisionRead] = None