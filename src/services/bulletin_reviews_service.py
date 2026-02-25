from typing import List, Optional
from bson import ObjectId
from fastapi import HTTPException
from acb_orm.collections.bulletin_reviews import BulletinReviews
from acb_orm.auxiliaries.target_element import TargetElement
from acb_orm.auxiliaries.review_cycle import ReviewCycle
from acb_orm.auxiliaries.comment import Comment
from acb_orm.collections.users import User
from acb_orm.auxiliaries.log import Log
from datetime import datetime
from tools.logger import logger
from tools.utils import serialize_log
import uuid


class BulletinReviewsService:
    """Service for managing bulletin reviews, cycles, and comments"""
    
    @staticmethod
    def _serialize_document(document) -> dict:
        """Serialize BulletinReviews document to dict"""
        data = document.to_mongo().to_dict()
        if '_id' in data:
            data['id'] = str(data['_id'])
            del data['_id']
        if 'bulletin_master_id' in data:
            data['bulletin_master_id'] = str(data['bulletin_master_id'])
        
        # Serialize reviewer_user_id and fetch reviewer details
        if 'reviewer_user_id' in data and data['reviewer_user_id']:
            reviewer_id = data['reviewer_user_id']
            data['reviewer_user_id'] = str(reviewer_id)
            
            # Fetch reviewer details from User collection
            try:
                reviewer = User.objects(id=reviewer_id).first()
                if reviewer:
                    data['reviewer_first_name'] = reviewer.first_name
                    data['reviewer_last_name'] = reviewer.last_name
                else:
                    data['reviewer_first_name'] = None
                    data['reviewer_last_name'] = None
            except Exception as e:
                logger.warning(f"Could not fetch reviewer details for {reviewer_id}: {e}")
                data['reviewer_first_name'] = None
                data['reviewer_last_name'] = None
        else:
            data['reviewer_first_name'] = None
            data['reviewer_last_name'] = None
        
        if 'log' in data:
            data['log'] = serialize_log(document.log)
        # Serialize review_cycles
        if 'review_cycles' in data:
            for cycle in data['review_cycles']:
                if 'bulletin_version_id' in cycle and cycle['bulletin_version_id']:
                    cycle['bulletin_version_id'] = str(cycle['bulletin_version_id'])
        
        # Serialize comments recursively
        if 'comments' in data:
            data['comments'] = [BulletinReviewsService._serialize_comment(c) for c in data['comments']]
        
        return data
    
    @staticmethod
    def _serialize_comment(comment) -> dict:
        """Recursively serialize comment with author details"""
        if isinstance(comment, dict):
            c_dict = comment
        else:
            c_dict = comment.to_mongo().to_dict()
        
        # Serialize author_id and fetch author details
        if 'author_id' in c_dict and c_dict['author_id']:
            author_id = c_dict['author_id']
            c_dict['author_id'] = str(author_id)
            
            # Fetch author details from User collection
            try:
                author = User.objects(id=author_id).first()
                if author:
                    c_dict['author_first_name'] = author.first_name
                    c_dict['author_last_name'] = author.last_name
                else:
                    c_dict['author_first_name'] = None
                    c_dict['author_last_name'] = None
            except Exception as e:
                logger.warning(f"Could not fetch author details for {author_id}: {e}")
                c_dict['author_first_name'] = None
                c_dict['author_last_name'] = None
        
        if 'bulletin_version_id' in c_dict and c_dict['bulletin_version_id']:
            c_dict['bulletin_version_id'] = str(c_dict['bulletin_version_id'])
        
        # Recursively serialize replies
        if 'replies' in c_dict and c_dict['replies']:
            c_dict['replies'] = [BulletinReviewsService._serialize_comment(r) for r in c_dict['replies']]
        
        return c_dict
    
    def get_or_create_review(self, bulletin_master_id: str, user_id: str) -> BulletinReviews:
        """Get existing review or create new one for a bulletin"""
        if not ObjectId.is_valid(bulletin_master_id):
            raise HTTPException(status_code=400, detail="Invalid bulletin master ID")
        
        review = BulletinReviews.objects(bulletin_master_id=ObjectId(bulletin_master_id)).first()
        
        if not review:
            log = Log(
                creator_user_id=ObjectId(user_id),
                created_at=datetime.now(),
                updater_user_id=ObjectId(user_id),
                updated_at=datetime.now()
            )
            review = BulletinReviews(
                bulletin_master_id=ObjectId(bulletin_master_id),
                log=log,
                review_cycles=[],
                comments=[]
            )
            review.save()
            logger.info(f"Created new BulletinReview for bulletin {bulletin_master_id}")
        
        return review
    
    def add_review_cycle(self, bulletin_master_id: str, bulletin_version_id: str, user_id: str) -> BulletinReviews:
        """Add a new review cycle when bulletin is submitted for review"""
        review = self.get_or_create_review(bulletin_master_id, user_id)
        
        cycle_number = len(review.review_cycles) + 1
        new_cycle = ReviewCycle(
            cycle_number=cycle_number,
            bulletin_version_id=ObjectId(bulletin_version_id),
            submitted_at=datetime.now(),
            outcome=None
        )
        
        review.review_cycles.append(new_cycle)
        review.log.updater_user_id = ObjectId(user_id)
        review.log.updated_at = datetime.now()
        review.save()
        
        logger.info(f"Added review cycle {cycle_number} for bulletin {bulletin_master_id}")
        return review
    
    def assign_reviewer(self, bulletin_master_id: str, reviewer_user_id: str, user_id: str) -> BulletinReviews:
        """Assign reviewer to the bulletin review"""
        review = self.get_or_create_review(bulletin_master_id, user_id)
        
        review.reviewer_user_id = ObjectId(reviewer_user_id)
        review.log.updater_user_id = ObjectId(user_id)
        review.log.updated_at = datetime.now()
        review.save()
        
        return review
    
    def complete_cycle(self, bulletin_master_id: str, outcome: str, user_id: str) -> BulletinReviews:
        """Complete the current review cycle with outcome (approved/rejected)"""
        review = BulletinReviews.objects(bulletin_master_id=ObjectId(bulletin_master_id)).first()
        
        if not review or not review.review_cycles:
            raise HTTPException(status_code=404, detail="No active review cycle found")
        
        current_cycle = review.review_cycles[-1]
        current_cycle.completed_at = datetime.now()
        current_cycle.outcome = outcome
        
        review.log.updater_user_id = ObjectId(user_id)
        review.log.updated_at = datetime.now()
        review.save()
        
        logger.info(f"Completed review cycle for bulletin {bulletin_master_id} with outcome: {outcome}")
        return review
    
    def add_comment(self, bulletin_master_id: str, bulletin_version_id: str, text: str, 
                    author_id: str, target_element: Optional[dict] = None,
                    parent_comment_id: Optional[str] = None) -> dict:
        """Add a comment or reply to the review. Creates the review if it doesn't exist.
        The comment_path is derived automatically from the parent's path."""
        review = self.get_or_create_review(bulletin_master_id, author_id)
        
        comment_id = str(uuid.uuid4())
        
        # Build comment_path: derive from parent if reply, otherwise root
        if parent_comment_id:
            parent_path = self._find_comment_path(review.comments, parent_comment_id)
            if not parent_path:
                raise HTTPException(status_code=404, detail="Parent comment not found")
            comment_path = f"{parent_path}/{comment_id}"
        else:
            comment_path = comment_id
        
        # Create comment object
        target_elem = None
        if target_element:
            target_elem = TargetElement(**target_element)
        
        new_comment = Comment(
            comment_id=comment_id,
            parent_comment_id=parent_comment_id,
            comment_path=comment_path,
            bulletin_version_id=ObjectId(bulletin_version_id),
            text=text,
            author_id=ObjectId(author_id),
            created_at=datetime.now(),
            target_element=target_elem,
            is_editable=True
        )
        
        # If it's a reply, find parent and add to its replies
        if parent_comment_id:
            parent_found = self._add_reply_to_parent(review.comments, parent_comment_id, new_comment)
            if not parent_found:
                raise HTTPException(status_code=404, detail="Parent comment not found")
        else:
            # It's a root comment
            review.comments.append(new_comment)
        
        review.log.updater_user_id = ObjectId(author_id)
        review.log.updated_at = datetime.now()
        review.save()
        
        logger.info(f"Added comment {comment_id} to bulletin {bulletin_master_id}")
        
        # Return serialized comment
        return self._serialize_comment(new_comment)
    
    def edit_comment(self, bulletin_master_id: str, comment_id: str, new_text: str, user_id: str) -> dict:
        """Edit a comment's text. Only the original author can edit, and only if is_editable."""
        review = BulletinReviews.objects(bulletin_master_id=ObjectId(bulletin_master_id)).first()
        if not review:
            raise HTTPException(status_code=404, detail="Review not found")
        
        comment = self._find_comment(review.comments, comment_id)
        if not comment:
            raise HTTPException(status_code=404, detail="Comment not found")
        
        if not comment.is_editable:
            raise HTTPException(status_code=403, detail="This comment is no longer editable")
        
        if str(comment.author_id.id) != user_id:
            raise HTTPException(status_code=403, detail="Only the author can edit this comment")
        
        comment.text = new_text
        review.log.updater_user_id = ObjectId(user_id)
        review.log.updated_at = datetime.now()
        review.save()
        
        logger.info(f"Comment {comment_id} edited by user {user_id}")
        return self._serialize_comment(comment)
    
    def delete_comment(self, bulletin_master_id: str, comment_id: str, user_id: str) -> bool:
        """Delete a comment. Only the original author can delete, and only if is_editable.
        If the comment has replies, they are also removed."""
        review = BulletinReviews.objects(bulletin_master_id=ObjectId(bulletin_master_id)).first()
        if not review:
            raise HTTPException(status_code=404, detail="Review not found")
        
        comment = self._find_comment(review.comments, comment_id)
        if not comment:
            raise HTTPException(status_code=404, detail="Comment not found")
        
        if not comment.is_editable:
            raise HTTPException(status_code=403, detail="This comment is no longer editable and cannot be deleted")
        
        if str(comment.author_id.id) != user_id:
            raise HTTPException(status_code=403, detail="Only the author can delete this comment")
        
        removed = self._remove_comment(review.comments, comment_id)
        if not removed:
            raise HTTPException(status_code=404, detail="Comment not found during removal")
        
        review.log.updater_user_id = ObjectId(user_id)
        review.log.updated_at = datetime.now()
        review.save()
        
        logger.info(f"Comment {comment_id} deleted by user {user_id}")
        return True
    
    def _find_comment_path(self, comments: List[Comment], comment_id: str) -> Optional[str]:
        """Recursively find a comment by ID and return its comment_path"""
        for comment in comments:
            if comment.comment_id == comment_id:
                return comment.comment_path
            if comment.replies:
                result = self._find_comment_path(comment.replies, comment_id)
                if result:
                    return result
        return None
    
    def _find_comment(self, comments: List[Comment], comment_id: str) -> Optional[Comment]:
        """Recursively find a comment by ID and return the Comment object"""
        for comment in comments:
            if comment.comment_id == comment_id:
                return comment
            if comment.replies:
                result = self._find_comment(comment.replies, comment_id)
                if result:
                    return result
        return None
    
    def _remove_comment(self, comments: List[Comment], comment_id: str) -> bool:
        """Recursively find and remove a comment by ID from the tree"""
        for i, comment in enumerate(comments):
            if comment.comment_id == comment_id:
                comments.pop(i)
                return True
            if comment.replies:
                if self._remove_comment(comment.replies, comment_id):
                    return True
        return False
    
    def _add_reply_to_parent(self, comments: List[Comment], parent_id: str, reply: Comment) -> bool:
        """Recursively find parent comment and add reply"""
        for comment in comments:
            if comment.comment_id == parent_id:
                comment.replies.append(reply)
                return True
            if comment.replies:
                if self._add_reply_to_parent(comment.replies, parent_id, reply):
                    return True
        return False
    
    def mark_all_editable_not_editable(self, bulletin_master_id: str):
        """Mark ALL currently editable comments as not editable.
        Used during state transitions (PENDING→REVIEW, REJECTED→DRAFT)."""
        review = BulletinReviews.objects(bulletin_master_id=ObjectId(bulletin_master_id)).first()
        if not review:
            return
        
        self._set_editable_false(review.comments)
        review.save()
        logger.info(f"Marked all editable comments as not editable for bulletin {bulletin_master_id}")
    
    def _set_editable_false(self, comments: List[Comment]):
        """Recursively set is_editable=False on comments that are currently editable"""
        for comment in comments:
            if comment.is_editable:
                comment.is_editable = False
            if comment.replies:
                self._set_editable_false(comment.replies)
    
    def get_review_by_bulletin(self, bulletin_master_id: str) -> Optional[BulletinReviews]:
        """Get review document for a bulletin"""
        if not ObjectId.is_valid(bulletin_master_id):
            return None
        return BulletinReviews.objects(bulletin_master_id=ObjectId(bulletin_master_id)).first()
    
    def mark_comments_not_editable(self, bulletin_master_id: str, version_id: str):
        """Mark all comments from a specific version as not editable"""
        review = BulletinReviews.objects(bulletin_master_id=ObjectId(bulletin_master_id)).first()
        if not review:
            return
        
        self._mark_comment_tree_not_editable(review.comments, version_id)
        review.save()
        logger.info(f"Marked comments not editable for version {version_id}")
    
    def _mark_comment_tree_not_editable(self, comments: List[Comment], version_id: str):
        """Recursively mark comments as not editable"""
        for comment in comments:
            if str(comment.bulletin_version_id.id) == version_id:
                comment.is_editable = False
            if comment.replies:
                self._mark_comment_tree_not_editable(comment.replies, version_id)
    
    def get_comments_by_cycle(self, bulletin_master_id: str, cycle_number: int) -> List[dict]:
        """Get all comments for a specific review cycle"""
        review = self.get_review_by_bulletin(bulletin_master_id)
        if not review or cycle_number > len(review.review_cycles):
            return []
        
        cycle = review.review_cycles[cycle_number - 1]
        version_id = str(cycle.bulletin_version_id.id)
        
        # Filter comments by version_id
        filtered_comments = []
        for comment in review.comments:
            filtered = self._filter_comments_by_version(comment, version_id)
            if filtered:
                filtered_comments.append(filtered)
        
        return [self._serialize_comment(c) for c in filtered_comments]
    
    def _filter_comments_by_version(self, comment: Comment, version_id: str) -> Optional[Comment]:
        """Recursively filter comment tree by version"""
        if str(comment.bulletin_version_id.id) == version_id:
            return comment
        
        # Check replies
        if comment.replies:
            for reply in comment.replies:
                filtered = self._filter_comments_by_version(reply, version_id)
                if filtered:
                    return filtered
        
        return None
    
    def count_comments_in_cycle(self, bulletin_master_id: str) -> int:
        """Count comments in the current (last) review cycle"""
        review = self.get_review_by_bulletin(bulletin_master_id)
        if not review or not review.review_cycles:
            return 0
        
        current_cycle = review.review_cycles[-1]
        version_id = str(current_cycle.bulletin_version_id.id)
        
        return self._count_comments_by_version(review.comments, version_id)
    
    def _count_comments_by_version(self, comments: List[Comment], version_id: str) -> int:
        """Recursively count comments for a specific version"""
        count = 0
        for comment in comments:
            if str(comment.bulletin_version_id.id) == version_id:
                count += 1
            if comment.replies:
                count += self._count_comments_by_version(comment.replies, version_id)
        return count
