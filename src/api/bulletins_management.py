from fastapi import APIRouter, HTTPException, Depends, Path
from typing import List
from bson import ObjectId
from services.bulletins_master_service import BulletinsMasterService
from services.bulletins_version_service import BulletinsVersionService
from acb_orm.schemas.bulletins_master_schema import BulletinsMasterCreate, BulletinsMasterUpdate, BulletinsMasterRead
from acb_orm.schemas.bulletins_version_schema import BulletinsVersionRead, BulletinsVersionCreate, BulletinsVersionUpdate
from acb_orm.enums.status_bulletin import StatusBulletin
from auth.access_utils import get_current_user, user_has_permission
from schemas.response_models import BulletinWithCurrentVersion
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

router = APIRouter(prefix="/bulletins", tags=["Bulletin Management"])
bulletins_master_service = BulletinsMasterService()
bulletins_version_service = BulletinsVersionService()
security = HTTPBearer()


# --- CRUD and queries for bulletin masters ---

@router.post("/", response_model=BulletinsMasterRead)
def create_bulletin(
    bulletin: BulletinsMasterCreate = ...,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Creates a new bulletin master document.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    return bulletins_master_service.create(bulletin, user_id, 'bulletins_composer')

@router.put("/{bulletin_id}", response_model=BulletinsMasterRead)
def update_bulletin(
    bulletin_id: str = Path(..., description="ID of the bulletin to update"),
    bulletin: BulletinsMasterUpdate = ...,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Updates a bulletin master document by its ID. Checks permissions and updates the log with user info.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    return bulletins_master_service.update(bulletin_id, bulletin, user_id, 'bulletins_composer')

@router.get("/", response_model=List[BulletinsMasterRead])
def get_all_bulletins(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Returns all bulletins accessible to the current user.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    return bulletins_master_service.get_accessible_resources(user_id)

@router.get("/name/{name}", response_model=List[BulletinsMasterRead])
def get_bulletins_by_name(
    name: str = Path(..., description="Nombre o substring del boletín"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Returns bulletins whose name contains the given substring (case-insensitive).
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    filters = {"bulletin_name__icontains": name}
    return bulletins_master_service.get_accessible_resources(user_id, filters)

@router.get("/status/{status}", response_model=List[BulletinsMasterRead])
def get_bulletins_by_status(
    status: str = Path(..., description=f"Template status. Possible options: {list(StatusBulletin._value2member_map_.keys())}"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Returns bulletins by status, validating against allowed values.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    # Validate that the status is allowed
    if status not in StatusBulletin._value2member_map_:
        allowed = list(StatusBulletin._value2member_map_.keys())
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}. Allowed: {allowed}")
    filters = {"status": status}
    return bulletins_master_service.get_accessible_resources(user_id, filters)

@router.get("/{bulletin_id}", response_model=BulletinsMasterRead)
def get_bulletin_by_id(
    bulletin_id: str = Path(..., description="Bulletin ID"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Returns a bulletin by its ID if accessible to the user.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    bulletins = bulletins_master_service.get_accessible_resources(user_id, filters={"id": bulletin_id})
    if not bulletins:
        raise HTTPException(status_code=404, detail="Not found or no access")
    return bulletins[0]

@router.get("/{bulletin_id}/current-version", response_model=BulletinWithCurrentVersion)
def get_current_version(
    bulletin_id: str = Path(..., description="ID del boletín"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Returns the bulletin master and its current version by bulletin ID, validating user access.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    
    # Verify access to the bulletin master
    bulletins = bulletins_master_service.get_accessible_resources(user_id, filters={"id": bulletin_id})
    if not bulletins:
        raise HTTPException(status_code=404, detail="Not found or no access")
    
    bulletin_master = bulletins[0]
    
    version_id = bulletins_master_service.get_current_version_id(bulletin_id)
    if not version_id:
        raise HTTPException(status_code=404, detail="No current version found")
    
    try:
        current_version = bulletins_version_service.read_schema.model_validate(bulletins_version_service._serialize_document(version_id))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error retrieving current version")
    
    return BulletinWithCurrentVersion(
        bulletin_master=bulletin_master,
        current_version=current_version
    )

# --- CRUD and queries for bulletin versions ---

@router.post("/versions", response_model=BulletinsVersionRead)
def create_bulletin_version(
    version: BulletinsVersionCreate = ...,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Creates a new version for a bulletin and updates the master with the new current_version_id.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    bulletins = bulletins_master_service.get_accessible_resources(user_id, filters={"id": version.bulletin_master_id})
    if not bulletins:
        raise HTTPException(status_code=404, detail="Not found or no access")
    bulletin_master = bulletins[0]
    previous_version_id = getattr(bulletin_master, "current_version_id", None)
    version_data = version.model_dump()
    if previous_version_id:
        version_data["previous_version_id"] = previous_version_id
        previous_num =  bulletins_version_service.get_by_id(str(previous_version_id)).version_num
        version_data["version_num"] = previous_num + 1
    else:
        version_data["version_num"] = 1
    version_obj = bulletins_version_service.create(BulletinsVersionCreate(**version_data), user_id)
    # Update the master with the new current_version_id
    update_data = BulletinsMasterUpdate(current_version_id=str(version_obj.id))
    bulletins_master_service.update(version.bulletin_master_id, update_data, user_id)
    return version_obj

@router.get("/{bulletin_id}/history", response_model=List[BulletinsVersionRead])
def get_bulletin_history(
    bulletin_id: str = Path(..., description="ID del boletín"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Returns the version history for a bulletin, ordered from most recent to oldest.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    bulletins = bulletins_master_service.get_accessible_resources(user_id, filters={"id": bulletin_id})
    if not bulletins:
        raise HTTPException(status_code=404, detail="Not found or no access")
    history = bulletins_version_service.get_by_master_id(bulletin_id)
    return history

@router.get("/version/{version_id}", response_model=BulletinsVersionRead)
def get_version_by_id(
    version_id: str = Path(..., description="ID de la versión"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Returns a bulletin version by its ID.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    return bulletins_version_service.get_by_id(version_id)

