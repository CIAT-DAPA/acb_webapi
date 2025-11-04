import re
from fastapi import HTTPException
from bson import ObjectId
from typing import List
from acb_orm.collections.users import User

def parse_object_ids(ids_str: str) -> List[str]:
    """Parse and validate a comma-separated string of ObjectIds."""
    ids = [id.strip() for id in ids_str.split(",") if id.strip()]
    invalid = [i for i in ids if not ObjectId.is_valid(i)]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid ObjectIds: {', '.join(invalid)}"
        )
    return ids

def build_search_query(terms: List[str], fields: List[str]) -> dict:
    """Construct a raw MongoDB OR query using regex for partial match."""
    safe_terms = [re.escape(term.strip()) for term in terms if term.strip()]
    return {
        "$or": [
            {field: {"$regex": term, "$options": "i"}}
            for term in safe_terms
            for field in fields
        ]
    }

def serialize_log(log_obj):
    if log_obj is None:
        return None
    log_dict = log_obj.to_mongo().to_dict()  
    
    for key in ["creator_user_id", "updater_user_id"]:
        if key in log_dict and log_dict[key] is not None:
            user_id = str(log_dict[key])
            log_dict[key] = user_id
            
            try:
                user = User.objects(id=user_id).first()
                if user:
                    if key == "creator_user_id":
                        log_dict["creator_first_name"] = getattr(user, 'first_name', None)
                        log_dict["creator_last_name"] = getattr(user, 'last_name', None)
                    elif key == "updater_user_id":
                        log_dict["updater_first_name"] = getattr(user, 'first_name', None)
                        log_dict["updater_last_name"] = getattr(user, 'last_name', None)
            except Exception:
                pass
    
    return log_dict