from fastapi import APIRouter, HTTPException, Depends, Path
from typing import List, Dict, Set
from bson import ObjectId
from services.bulletins_master_service import BulletinsMasterService
from services.bulletins_version_service import BulletinsVersionService
from services.cards_service import CardsService
from acb_orm.schemas.bulletins_master_schema import BulletinsMasterCreate, BulletinsMasterUpdate, BulletinsMasterRead
from acb_orm.schemas.bulletins_version_schema import BulletinsVersionRead, BulletinsVersionCreate, BulletinsVersionUpdate
from acb_orm.schemas.cards_schema import CardsRead
from acb_orm.enums.status_bulletin import StatusBulletin
from auth.access_utils import get_current_user, user_has_permission
from schemas.response_models import BulletinWithCurrentVersion, BulletinWithCurrentVersionPublic
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

router = APIRouter(prefix="/bulletins", tags=["Bulletin Management"])
bulletins_master_service = BulletinsMasterService()
bulletins_version_service = BulletinsVersionService()
cards_service = CardsService()
security = HTTPBearer()


def extract_card_ids_from_data(data: dict) -> Set[str]:
    """Recursively extract all cardId values from bulletin data."""
    card_ids = set()
    
    sections = data.get("sections", [])
    for section in sections:
        blocks = section.get("blocks", [])
        for block in blocks:
            fields = block.get("fields", [])
            for field in fields:
                if field.get("type") == "card":
                    values = field.get("value", [])
                    for value_item in values:
                        if isinstance(value_item, dict) and "cardId" in value_item:
                            card_ids.add(value_item["cardId"])
    
    return card_ids


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

@router.get("/slug_name", response_model=list[str], include_in_schema=False)
def get_all_bulletin_slug_names(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Returns a list of all bulletin slug names.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    bulletins = bulletins_master_service.get_all()
    slug_names = [bulletin.name_machine for bulletin in bulletins if hasattr(bulletin, 'name_machine') and bulletin.name_machine is not None]
    return slug_names

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
        master=bulletin_master,
        current_version=current_version
    )


@router.get("/{bulletin_id}/current-version-published", response_model=BulletinWithCurrentVersionPublic)
def get_current_version_published(
    bulletin_id: str = Path(..., description="ID del boletín"),
):
    """
    Public endpoint that returns the bulletin master and its current version 
    ONLY if the bulletin status is PUBLISHED. No authentication required.
    Includes cards metadata for all cards referenced in the bulletin data.
    Returns 404 if the bulletin doesn't exist or is not published.
    """
    
    # Get bulletin master without authentication
    bulletin_master = bulletins_master_service.get_by_id(id=bulletin_id)
    if not bulletin_master:
        raise HTTPException(status_code=404, detail="Bulletin not found")
    
    # Verify the bulletin is PUBLISHED (security check for public access)
    if bulletin_master.status != StatusBulletin.PUBLISHED:
        raise HTTPException(status_code=404, detail="Bulletin not found")
    
    # Get the current version
    version_id = bulletins_master_service.get_current_version_id(bulletin_id)
    if not version_id:
        raise HTTPException(status_code=404, detail="Bulletin not found")
    
    try:
        current_version = bulletins_version_service.read_schema.model_validate(
            bulletins_version_service._serialize_document(version_id)
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail="Bulletin not found")
    
    # Extract all card IDs from the bulletin data
    card_ids = extract_card_ids_from_data(current_version.data)
    
    # Fetch all cards in bulk and create a dict indexed by card ID
    cards_metadata: Dict[str, CardsRead] = {}
    if card_ids:
        try:
            # Convert set to comma-separated string for get_by_ids
            card_ids_str = ",".join(card_ids)
            cards = cards_service.get_by_ids(card_ids_str)
            
            # Index cards by their ID
            for card in cards:
                cards_metadata[card.id] = card
        except Exception as e:
            # If cards fetch fails, continue without cards (graceful degradation)
            pass
    
    return BulletinWithCurrentVersionPublic(
        master=bulletin_master,
        current_version=current_version,
        cards_metadata=cards_metadata
    )

@router.get("/by-slug/{bulletinSlug}", response_model=BulletinWithCurrentVersionPublic)
def get_current_version_published_by_slug(
    bulletinSlug: str = Path(..., description="Slug del boletín"),
):
    """
    Public endpoint that returns the bulletin master and its current version 
    ONLY if the bulletin status is PUBLISHED. No authentication required.
    Includes cards metadata for all cards referenced in the bulletin data.
    Returns 404 if the bulletin doesn't exist or is not published.
    """
    
    # Get bulletin master without authentication
    bulletin_master = bulletins_master_service._get_by_field(field="name_machine", value=bulletinSlug)
    if not bulletin_master:
        raise HTTPException(status_code=404, detail="Bulletin not found")
    
    bulletin_master = bulletin_master[0]
    
    # Verify the bulletin is PUBLISHED (security check for public access)
    if bulletin_master.status != StatusBulletin.PUBLISHED:
        raise HTTPException(status_code=404, detail="Bulletin not found")
    
    bulletin_id = str(bulletin_master.id)
    
    # Get the current version
    version_id = bulletins_master_service.get_current_version_id(bulletin_id)
    if not version_id:
        raise HTTPException(status_code=404, detail="Bulletin not found")
    
    try:
        current_version = bulletins_version_service.read_schema.model_validate(
            bulletins_version_service._serialize_document(version_id)
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail="Bulletin not found")
    
    # Extract all card IDs from the bulletin data
    card_ids = extract_card_ids_from_data(current_version.data)
    
    # Fetch all cards in bulk and create a dict indexed by card ID
    cards_metadata: Dict[str, CardsRead] = {}
    if card_ids:
        try:
            # Convert set to comma-separated string for get_by_ids
            card_ids_str = ",".join(card_ids)
            cards = cards_service.get_by_ids(card_ids_str)
            
            # Index cards by their ID
            for card in cards:
                cards_metadata[card.id] = card
        except Exception as e:
            # If cards fetch fails, continue without cards (graceful degradation)
            pass
    
    return BulletinWithCurrentVersionPublic(
        master=bulletin_master,
        current_version=current_version,
        cards_metadata=cards_metadata
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

