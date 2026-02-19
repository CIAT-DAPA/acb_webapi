from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from acb_orm.schemas.log_schema import LogRead
from acb_orm.schemas.comment_schema import TargetElementSchema

class TargetElementRead(BaseModel):
    """Schema for target element in comments (local, used by CommentRead)"""
    section_id: Optional[str] = None
    block_id: Optional[str] = None
    field_id: Optional[str] = None

class CommentRead(BaseModel):
    """Schema for reading comments with expanded author info"""
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
    replies: List['CommentRead'] = []
    is_editable: bool = True
    
    model_config = ConfigDict(from_attributes=True)

class CommentCreateRequest(BaseModel):
    """Schema for creating a comment via API request.
    Uses TargetElementSchema from ORM which validates dependency hierarchy
    (field_id requires block_id and section_id, block_id requires section_id).
    Only parent_comment_id is needed for replies; comment_path is derived server-side.
    """
    text: str = Field(..., min_length=1)
    target_element: Optional[TargetElementSchema] = None
    parent_comment_id: Optional[str] = None

class CommentUpdateRequest(BaseModel):
    """Schema for updating a comment's text. Only the author can edit."""
    text: str = Field(..., min_length=1)

class CommentCreateResponse(BaseModel):
    """Schema for the response after creating a comment (full comment data)"""
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
    """Schema for reading review cycles"""
    cycle_number: int
    bulletin_version_id: str
    submitted_at: datetime
    completed_at: Optional[datetime] = None
    outcome: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)

class BulletinReviewRead(BaseModel):
    """Schema for reading bulletin review with all cycles and comments"""
    id: str
    bulletin_master_id: str
    reviewer_user_id: Optional[str] = None
    reviewer_first_name: Optional[str] = None
    reviewer_last_name: Optional[str] = None
    review_cycles: List[ReviewCycleRead] = []
    comments: List[CommentRead] = []
    log: LogRead
    
    model_config = ConfigDict(from_attributes=True)
