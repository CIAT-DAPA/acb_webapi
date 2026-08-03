from fastapi import APIRouter, HTTPException, Depends, Path, Body
from typing import List, Optional
from services.bulletins_master_service import BulletinsMasterService
from services.bulletin_reviews_service import BulletinReviewsService
from services.users_service import UsersService
from acb_orm.schemas.bulletins_master_schema import BulletinsMasterRead, BulletinsMasterUpdate
from acb_orm.schemas.bulletin_reviews_schema import BulletinReviewsRead
from acb_orm.schemas.comment_schema import CommentRead
from schemas.bulletin_reviews_schema import CommentCreateRequest, CommentCreateResponse, CommentUpdateRequest
from acb_orm.enums.outcome_cycle import OutcomeCycle
from acb_orm.enums.status_bulletin import StatusBulletin
from auth.access_utils import (
    get_current_user,
    user_has_permission,
)
from constants.permissions import MODULE_REVIEW, ACTION_CREATE, ACTION_READ, ACTION_UPDATE, ACTION_DELETE
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from tools.logger import logger

router = APIRouter(prefix="/bulletins/reviews", tags=["Bulletin Reviews & Workflow"])
bulletins_master_service = BulletinsMasterService()
bulletin_reviews_service = BulletinReviewsService()
users_service = UsersService()
security = HTTPBearer()

def get_bulletin_groups(bulletin) -> List[str]:
    """
    Return the group IDs associated with the bulletin.
    """
    access_config = getattr(
        bulletin,
        "access_config",
        None,
    )

    allowed_groups = getattr(
        access_config,
        "allowed_groups",
        [],
    ) or []

    return [
        str(group.id) if hasattr(group, "id") else str(group)
        for group in allowed_groups
    ]


def has_review_permissions_for_bulletin(
    user_id: str,
    bulletin_groups: List[str],
    required_actions: List[str],
) -> bool:
    """
    Return True when the user has every requested REVIEW permission
    in at least one of the bulletin's groups.
    """
    for group_id in bulletin_groups:
        has_all_permissions = all(
            user_has_permission(
                user_id,
                group_id,
                MODULE_REVIEW,
                action,
            )
            for action in required_actions
        )

        if has_all_permissions:
            return True

    return False


def has_review_crud_for_bulletin(
    user_id: str,
    bulletin_groups: List[str],
) -> bool:
    """
    Return True when the user has full CRUD permissions
    in the REVIEW module for at least one bulletin group.
    """
    return has_review_permissions_for_bulletin(
        user_id,
        bulletin_groups,
        [
            ACTION_CREATE,
            ACTION_READ,
            ACTION_UPDATE,
            ACTION_DELETE,
        ],
    )


def require_review_permissions(
    user_id: str,
    bulletin,
    required_actions: List[str],
    detail: str,
) -> None:
    """
    Raise 403 when the user does not have the requested permissions
    in the REVIEW module.
    """
    bulletin_groups = get_bulletin_groups(
        bulletin,
    )

    if not has_review_permissions_for_bulletin(
        user_id,
        bulletin_groups,
        required_actions,
    ):
        raise HTTPException(
            status_code=403,
            detail=detail,
        )
    
# --- WORKFLOW ENDPOINTS ---

@router.post("/{bulletin_id}/submit-for-review", response_model=BulletinsMasterRead)
def submit_for_review(
    bulletin_id: str = Path(..., description="Bulletin ID"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Submit bulletin for review (DRAFT → PENDING_REVIEW).
    Creates a new review cycle with the current version.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    
    # Check permissions
    bulletins = bulletins_master_service.get_accessible_resources(user_id, filters={"id": bulletin_id})
    if not bulletins:
        raise HTTPException(status_code=403, detail="No access to this bulletin")

    # Get bulletin
    bulletin = bulletins[0]
    if not bulletin:
        raise HTTPException(status_code=404, detail="Bulletin not found")
    
    # Validate status
    if bulletin.status != StatusBulletin.DRAFT:
        raise HTTPException(
            status_code=400,
            detail=f"Can only submit bulletins in DRAFT status. Current status: {bulletin.status.value}"
        )
    
    # Validate has current_version_id
    if not bulletin.current_version_id:
        raise HTTPException(status_code=400, detail="Bulletin has no current version")
    
    # Check if there are previous cycles
    review = bulletin_reviews_service.get_review_by_bulletin(bulletin_id)
    if review and review.review_cycles:
        last_cycle = review.review_cycles[-1]
        last_version_id = str(last_cycle.bulletin_version_id.id)
        current_version_id = str(bulletin.current_version_id)
        
        # Validate version changed (unless there are editor replies)
        if last_version_id == current_version_id:
            # Check if editor has replied to comments
            comment_count = bulletin_reviews_service.count_comments_in_cycle(bulletin_id)

            logger.debug(f"Last version ID: {last_version_id}, Current version ID: {current_version_id}, Comment count in cycle: {comment_count} last cycle outcome: {last_cycle.outcome}")
            if comment_count == 0 and last_cycle.outcome != OutcomeCycle.CANCELLED:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot resubmit same version without changes or comments"
                )
    
    # Change status
    update_data = BulletinsMasterUpdate(status=StatusBulletin.PENDING_REVIEW)
    updated_bulletin = bulletins_master_service.update(bulletin_id, update_data, user_id)
    
    # Add review cycle
    bulletin_reviews_service.add_review_cycle(
        bulletin_id,
        bulletin.current_version_id,
        user_id
    )
    
    logger.info(f"Bulletin {bulletin_id} submitted for review by user {user_id}")
    return updated_bulletin

@router.post("/{bulletin_id}/assign-reviewer", response_model=dict)
def assign_reviewer(
    bulletin_id: str = Path(..., description="Bulletin ID"),
    reviewer_user_id: str = Body(..., embed=True, description="User ID of reviewer"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Assign a reviewer to the bulletin (Admin only).
    Bulletin remains in PENDING_REVIEW until reviewer opens it.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    
    # Get bulletin
    bulletin = bulletins_master_service.get_by_id(bulletin_id)
    if not bulletin:
        raise HTTPException(status_code=404, detail="Bulletin not found")
    
    # Validate status
    if bulletin.status != StatusBulletin.PENDING_REVIEW:
        raise HTTPException(
            status_code=400,
            detail=f"Can only assign reviewer to bulletins in PENDING_REVIEW. Current: {bulletin.status.value}"
        )
    
    # Check if user is admin (superadmin or group admin)
    require_review_permissions(
        user_id,
        bulletin,
        [
            ACTION_READ,
            ACTION_UPDATE,
        ],
        (
            "REVIEW_READ and REVIEW_UPDATE permissions "
            "are required to assign reviewers"
        ),
    )
    
    # Assign reviewer
    bulletin_reviews_service.assign_reviewer(bulletin_id, reviewer_user_id, user_id)
    
    # Get reviewer info
    reviewer = users_service.get_by_id(reviewer_user_id)
    
    logger.info(f"Reviewer {reviewer_user_id} assigned to bulletin {bulletin_id} by {user_id}")
    
    return {
        "success": True,
        "reviewer": {
            "id": reviewer.id,
            "first_name": reviewer.first_name,
            "last_name": reviewer.last_name
        }
    }

@router.post("/{bulletin_id}/open-review", response_model=BulletinsMasterRead)
def open_review(
    bulletin_id: str = Path(..., description="Bulletin ID"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Open bulletin for review (PENDING_REVIEW → REVIEW).
    Can be done by any reviewer of the bulletin's groups or admin.
    If no reviewer is assigned, the user who opens it will be auto-assigned.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    
    # Get bulletin
    bulletin = bulletins_master_service.get_by_id(bulletin_id)
    if not bulletin:
        raise HTTPException(status_code=404, detail="Bulletin not found")
    
    # Validate status
    if bulletin.status != StatusBulletin.PENDING_REVIEW:
        raise HTTPException(
            status_code=400,
            detail=f"Can only open bulletins in PENDING_REVIEW. Current: {bulletin.status.value}"
        )
    
    # Check permissions (reviewer or admin)
    require_review_permissions(
        user_id,
        bulletin,
        [
            ACTION_READ,
            ACTION_UPDATE,
        ],
        (
            "REVIEW_READ and REVIEW_UPDATE permissions "
            "are required to open the review"
        ),
    )
    
    # Auto-assign reviewer if not assigned and user is a reviewer (not admin)
    review = bulletin_reviews_service.get_review_by_bulletin(
        bulletin_id
    )

    if not review or not review.reviewer_user_id:
        bulletin_reviews_service.assign_reviewer(
            bulletin_id,
            user_id,
            user_id,
        )

        logger.info(
            f"Auto-assigned review manager {user_id} "
            f"to bulletin {bulletin_id}"
        )

    # Close the editor comment window when review starts
    bulletin_reviews_service.mark_all_editable_not_editable(
        bulletin_id
    )

    # Change bulletin status from PENDING_REVIEW to REVIEW
    update_data = BulletinsMasterUpdate(
        status=StatusBulletin.REVIEW
    )

    updated_bulletin = bulletins_master_service.update(
        bulletin_id,
        update_data,
        user_id,
    )

    logger.info(
        f"Bulletin {bulletin_id} review opened "
        f"by user {user_id}"
    )

    return updated_bulletin

@router.post("/{bulletin_id}/approve", response_model=BulletinsMasterRead)
def approve_bulletin(
    bulletin_id: str = Path(..., description="Bulletin ID"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Approve bulletin (REVIEW → PUBLISHED).
    Can only be done by assigned reviewer or admin.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    
    # Get bulletin
    bulletin = bulletins_master_service.get_by_id(bulletin_id)
    if not bulletin:
        raise HTTPException(status_code=404, detail="Bulletin not found")
    
    # Validate status
    if bulletin.status != StatusBulletin.REVIEW:
        raise HTTPException(
            status_code=400,
            detail=f"Can only approve bulletins in REVIEW status. Current: {bulletin.status.value}"
        )
    
    # Check permissions
    require_review_permissions(
        user_id,
        bulletin,
        [
            ACTION_READ,
            ACTION_UPDATE,
        ],
        (
            "REVIEW_READ and REVIEW_UPDATE permissions "
            "are required to approve the bulletin"
        ),
    )
    
    # Complete review cycle
    bulletin_reviews_service.complete_cycle(bulletin_id, 'approved', user_id)
    
    # Mark comments as not editable
    review = bulletin_reviews_service.get_review_by_bulletin(bulletin_id)
    if review and review.review_cycles:
        version_id = str(review.review_cycles[-1].bulletin_version_id.id)
        bulletin_reviews_service.mark_comments_not_editable(bulletin_id, version_id)
    
    # Change status to PUBLISHED
    update_data = BulletinsMasterUpdate(status=StatusBulletin.PUBLISHED)
    updated_bulletin = bulletins_master_service.update(bulletin_id, update_data, user_id)
    
    logger.info(f"Bulletin {bulletin_id} approved by user {user_id}")
    return updated_bulletin

@router.post("/{bulletin_id}/reject", response_model=BulletinsMasterRead)
def reject_bulletin(
    bulletin_id: str = Path(..., description="Bulletin ID"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Reject bulletin (REVIEW → REJECTED).
    Requires at least one comment in the current cycle.
    Can only be done by assigned reviewer or admin.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    
    # Get bulletin
    bulletin = bulletins_master_service.get_by_id(bulletin_id)
    if not bulletin:
        raise HTTPException(status_code=404, detail="Bulletin not found")
    
    # Validate status
    if bulletin.status != StatusBulletin.REVIEW:
        raise HTTPException(
            status_code=400,
            detail=f"Can only reject bulletins in REVIEW status. Current: {bulletin.status.value}"
        )
    
    # Check permissions
    require_review_permissions(
        user_id,
        bulletin,
        [
            ACTION_READ,
            ACTION_UPDATE,
        ],
        (
            "REVIEW_READ and REVIEW_UPDATE permissions "
            "are required to reject the bulletin"
        ),
    )
    
    # Validate there's at least one comment in current cycle
    comment_count = bulletin_reviews_service.count_comments_in_cycle(bulletin_id)
    if comment_count == 0:
        raise HTTPException(
            status_code=400,
            detail="Cannot reject without comments. Please add at least one comment explaining the issues."
        )
    
    # Complete review cycle
    bulletin_reviews_service.complete_cycle(bulletin_id, 'rejected', user_id)
    
    # Mark comments as not editable
    review = bulletin_reviews_service.get_review_by_bulletin(bulletin_id)
    if review and review.review_cycles:
        version_id = str(review.review_cycles[-1].bulletin_version_id.id)
        bulletin_reviews_service.mark_comments_not_editable(bulletin_id, version_id)
    
    # Change status to REJECTED
    update_data = BulletinsMasterUpdate(status=StatusBulletin.REJECTED)
    updated_bulletin = bulletins_master_service.update(bulletin_id, update_data, user_id)
    
    logger.info(f"Bulletin {bulletin_id} rejected by user {user_id}")
    return updated_bulletin

@router.post("/{bulletin_id}/reopen", response_model=BulletinsMasterRead)
def reopen_bulletin(
    bulletin_id: str = Path(..., description="Bulletin ID"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Reopen rejected bulletin for editing (REJECTED → DRAFT).
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    
    # Get bulletin
    bulletin = bulletins_master_service.get_by_id(bulletin_id)
    if not bulletin:
        raise HTTPException(status_code=404, detail="Bulletin not found")
    
    # Validate status
    if bulletin.status != StatusBulletin.REJECTED:
        raise HTTPException(
            status_code=400,
            detail=f"Can only reopen bulletins in REJECTED status. Current: {bulletin.status.value}"
        )
    
    # Check permissions
    bulletins = bulletins_master_service.get_accessible_resources(user_id, filters={"id": bulletin_id})
    if not bulletins:
        raise HTTPException(status_code=403, detail="No access to this bulletin")
    
    # Mark all editable comments as not editable (reviewer's window is closed)
    bulletin_reviews_service.mark_all_editable_not_editable(bulletin_id)
    
    # Change status to DRAFT
    update_data = BulletinsMasterUpdate(status=StatusBulletin.DRAFT)
    updated_bulletin = bulletins_master_service.update(bulletin_id, update_data, user_id)
    
    logger.info(f"Bulletin {bulletin_id} reopened by user {user_id}")
    return updated_bulletin

@router.post("/{bulletin_id}/publish-direct", response_model=BulletinsMasterRead)
def publish_direct(
    bulletin_id: str = Path(..., description="Bulletin ID"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Publish bulletin directly without review (DRAFT → PUBLISHED).
    Allowed for admins or users with full CRUD in review module.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    
    # Get bulletin
    bulletin = bulletins_master_service.get_by_id(bulletin_id)
    if not bulletin:
        raise HTTPException(status_code=404, detail="Bulletin not found")
    
    # Validate status
    if bulletin.status != StatusBulletin.DRAFT:
        raise HTTPException(
            status_code=400,
            detail=f"Can only publish bulletins in DRAFT status. Current: {bulletin.status.value}"
        )

    bulletin_groups = get_bulletin_groups(
        bulletin,
    )

    if not has_review_crud_for_bulletin(
        user_id,
        bulletin_groups,
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "Full CRUD permissions in the REVIEW module "
                "are required to publish directly"
            ),
        )
    
    # Change status to PUBLISHED
    update_data = BulletinsMasterUpdate(status=StatusBulletin.PUBLISHED)
    updated_bulletin = bulletins_master_service.update(bulletin_id, update_data, user_id)
    
    logger.info(f"Bulletin {bulletin_id} published directly by user {user_id}")
    return updated_bulletin

@router.post("/{bulletin_id}/archive", response_model=BulletinsMasterRead)
def archive_bulletin(
    bulletin_id: str = Path(..., description="Bulletin ID"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Archive published bulletin (PUBLISHED → ARCHIVED).
    Admin only.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    
    # Get bulletin
    bulletin = bulletins_master_service.get_by_id(bulletin_id)
    if not bulletin:
        raise HTTPException(status_code=404, detail="Bulletin not found")
    
    # Validate status
    if bulletin.status != StatusBulletin.PUBLISHED:
        raise HTTPException(
            status_code=400,
            detail=f"Can only archive bulletins in PUBLISHED status. Current: {bulletin.status.value}"
        )
    
    require_review_permissions(
        user_id,
        bulletin,
        [
            ACTION_READ,
            ACTION_UPDATE,
        ],
        (
            "REVIEW_READ and REVIEW_UPDATE permissions "
            "are required to archive the bulletin"
        ),
    )
    # Change status to ARCHIVED
    update_data = BulletinsMasterUpdate(status=StatusBulletin.ARCHIVED)
    updated_bulletin = bulletins_master_service.update(bulletin_id, update_data, user_id)
    
    logger.info(f"Bulletin {bulletin_id} archived by admin {user_id}")
    return updated_bulletin

# --- COMMENTS ENDPOINTS ---

@router.post("/{bulletin_id}/comments", response_model=CommentCreateResponse)
def add_comment(
    bulletin_id: str = Path(..., description="Bulletin ID"),
    comment: CommentCreateRequest = ...,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Add a comment or reply to a bulletin review.
    Access rules by bulletin status:
    - PUBLISHED/ARCHIVED: No comments allowed.
    - REVIEW/REJECTED: Only reviewers + admins + superadmins.
    - DRAFT/PENDING_REVIEW with existing comments: Only editors + admins + superadmins.
    - DRAFT/PENDING_REVIEW without comments: No comments allowed (first comments must come in REVIEW).
    - No review exists: No comments allowed.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    
    # Get bulletin
    bulletin = bulletins_master_service.get_by_id(bulletin_id)
    if not bulletin:
        raise HTTPException(status_code=404, detail="Bulletin not found")
    
    # Check access
    bulletins = bulletins_master_service.get_accessible_resources(user_id, filters={"id": bulletin_id})
    if not bulletins:
        raise HTTPException(status_code=403, detail="No access to this bulletin")
    
    status = bulletin.status
    
    # 1. BLOQUEO absoluto: PUBLISHED / ARCHIVED
    if status in (StatusBulletin.PUBLISHED, StatusBulletin.ARCHIVED):
        raise HTTPException(
            status_code=403,
            detail="Comments are not allowed on published or archived bulletins"
        )
    
    # 2. Verificar que existe un review para este boletín
    review = bulletin_reviews_service.get_review_by_bulletin(bulletin_id)
    if not review:
        raise HTTPException(
            status_code=403,
            detail="This bulletin has no review yet. Comments cannot be added"
        )
    
    # 3. Verificar si el review tiene comentarios
    has_comments = len(review.comments) > 0

    if status in (
        StatusBulletin.REVIEW,
        StatusBulletin.REJECTED,
    ):
        require_review_permissions(
            user_id,
            bulletin,
            [
                ACTION_READ,
                ACTION_CREATE,
            ],
            (
                "REVIEW_READ and REVIEW_CREATE permissions "
                "are required to add comments during review"
            ),
        )

    elif status in (
        StatusBulletin.DRAFT,
        StatusBulletin.PENDING_REVIEW,
    ):
        if not has_comments:
            raise HTTPException(
                status_code=403,
                detail=(
                    "No comments can be added yet. "
                    "First comments must be created during review"
                ),
            )

        require_review_permissions(
            user_id,
            bulletin,
            [
                ACTION_READ,
                ACTION_CREATE,
            ],
            (
                "REVIEW_READ and REVIEW_CREATE permissions "
                "are required to reply to review comments"
            ),
        )
    
    # Add comment
    result = bulletin_reviews_service.add_comment(
        bulletin_master_id=bulletin_id,
        bulletin_version_id=str(bulletin.current_version_id),
        text=comment.text,
        author_id=user_id,
        target_element=comment.target_element.model_dump() if comment.target_element else None,
        parent_comment_id=comment.parent_comment_id
    )
    
    logger.info(f"Comment added to bulletin {bulletin_id} by user {user_id}")
    return result

@router.put("/{bulletin_id}/comments/{comment_id}", response_model=CommentCreateResponse)
def edit_comment(
    bulletin_id: str = Path(..., description="Bulletin ID"),
    comment_id: str = Path(..., description="Comment ID"),
    comment_update: CommentUpdateRequest = ...,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Edit a comment's text. Only the original author can edit.
    The comment must be editable (is_editable=True).
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    
    # Check access
    bulletins = bulletins_master_service.get_accessible_resources(user_id, filters={"id": bulletin_id})
    if not bulletins:
        raise HTTPException(status_code=403, detail="No access to this bulletin")
    
    result = bulletin_reviews_service.edit_comment(
        bulletin_master_id=bulletin_id,
        comment_id=comment_id,
        new_text=comment_update.text,
        user_id=user_id
    )
    
    logger.info(f"Comment {comment_id} edited in bulletin {bulletin_id} by user {user_id}")
    return result

@router.delete("/{bulletin_id}/comments/{comment_id}")
def delete_comment(
    bulletin_id: str = Path(..., description="Bulletin ID"),
    comment_id: str = Path(..., description="Comment ID"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Delete a comment. Only the original author can delete.
    The comment must be editable (is_editable=True).
    If the comment has replies, they are also removed.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    
    # Check access
    bulletins = bulletins_master_service.get_accessible_resources(user_id, filters={"id": bulletin_id})
    if not bulletins:
        raise HTTPException(status_code=403, detail="No access to this bulletin")
    
    bulletin_reviews_service.delete_comment(
        bulletin_master_id=bulletin_id,
        comment_id=comment_id,
        user_id=user_id
    )
    
    logger.info(f"Comment {comment_id} deleted from bulletin {bulletin_id} by user {user_id}")
    return {"success": True, "detail": "Comment deleted successfully"}

@router.get("/{bulletin_id}/review-history", response_model=BulletinReviewsRead)
def get_review_history(
    bulletin_id: str = Path(..., description="Bulletin ID"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get complete review history including all cycles and comments.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    
    # Check access
    bulletins = bulletins_master_service.get_accessible_resources(user_id, filters={"id": bulletin_id})
    if not bulletins:
        raise HTTPException(status_code=403, detail="No access to this bulletin")
    
    review = bulletin_reviews_service.get_review_by_bulletin(bulletin_id)
    if not review:
        raise HTTPException(status_code=404, detail="No review found for this bulletin")
    
    # Serialize review (serialization already expands reviewer and comment author info)
    review_data = bulletin_reviews_service._serialize_document(review)
    
    return review_data
