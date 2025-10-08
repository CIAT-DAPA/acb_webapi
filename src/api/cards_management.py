from fastapi import APIRouter, HTTPException, Depends, Path, Query
from typing import List, Optional
from services.cards_service import CardsService
from acb_orm.schemas.cards_schema import CardsCreate, CardsUpdate, CardsRead
from auth.access_utils import get_current_user, user_has_permission, get_user_groups
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from tools.utils import parse_object_ids

router = APIRouter(prefix="/cards", tags=["Cards Management"])
cards_service = CardsService()
security = HTTPBearer()

@router.post("/", response_model=CardsRead)
def create_card(
    card: CardsCreate = ...,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Creates a new card document.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    return cards_service.create(card, user_id, 'card_management')

@router.put("/{card_id}", response_model=CardsRead)
def update_card(
    card_id: str = Path(..., description="Unique identifier of the card to update"),
    card: CardsUpdate = ...,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Updates a card document by its ID. Checks permissions and updates the log with user info.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    return cards_service.update(card_id, card, user_id, 'card_management')

# @router.delete("/{card_id}")
# def delete_card(
#     card_id: str = Path(..., description="Unique identifier of the card to delete"),
#     credentials: HTTPAuthorizationCredentials = Depends(security)
# ):
#     """
#     Deletes a card document by its ID.
#     """
#     user = get_current_user(credentials)
#     user_id = user["user_db"]["id"]
#     cards_service.delete(card_id)
#     return {"success": True}

@router.get("/", response_model=List[CardsRead])
def get_all_cards(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Returns all cards accessible to the current user.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    return cards_service.get_accessible_resources(user_id)

@router.get("/name/{name}", response_model=List[CardsRead])
def get_cards_by_name(
    name: str = Path(..., description="Card name or substring to search for"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Returns cards whose name contains the given substring (case-insensitive).
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    filters = {"card_name__icontains": name}
    return cards_service.get_accessible_resources(user_id, filters)

@router.get("/type/{card_type}", response_model=List[CardsRead])
def get_cards_by_type(
    card_type: str = Path(..., description="Card type to filter by"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Returns cards by type.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    filters = {"card_type": card_type}
    return cards_service.get_accessible_resources(user_id, filters)

@router.get("/template/{template_id}", response_model=List[CardsRead])
def get_cards_by_template(
    template_id: str = Path(..., description="Template master ID to filter cards by"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Returns cards compatible with the given template master ID.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    # Usar el método específico del servicio para buscar por template_master_id
    all_cards = cards_service.get_by_template_master_id(template_id)
    # Filtrar solo los accesibles para el usuario
    accessible_card_ids = [card.id for card in cards_service.get_accessible_resources(user_id)]
    return [card for card in all_cards if card.id in accessible_card_ids]

@router.get("/by-groups/", response_model=List[CardsRead])
def get_cards_by_user_groups(
    group_ids: Optional[str] = Query(None, description="Comma-separated list of group IDs. If not provided, uses all user's groups."),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Returns cards accessible to the user based on their groups or specified group IDs.
    If group_ids is provided, filters cards by those specific groups.
    If group_ids is not provided, returns cards from all the user's groups.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    
    # Determinar los grupos a usar
    if group_ids:
        # Parsear los group_ids proporcionados
        requested_groups = parse_object_ids(group_ids)
        # Verificar que el usuario pertenezca a esos grupos
        user_groups = get_user_groups(user_id)
        user_group_strs = [str(gid) for gid in user_groups]
        # Filtrar solo los grupos a los que el usuario tiene acceso
        valid_groups = [gid for gid in requested_groups if gid in user_group_strs]
        if not valid_groups:
            raise HTTPException(status_code=403, detail="User does not belong to any of the specified groups")
        target_groups = valid_groups
    else:
        # Usar todos los grupos del usuario
        user_groups = get_user_groups(user_id)
        target_groups = [str(gid) for gid in user_groups]
    
    # Obtener todas las cards accesibles al usuario
    all_accessible_cards = cards_service.get_accessible_resources(user_id)
    
    # Filtrar cards que pertenecen a los grupos objetivo
    filtered_cards = [
        card for card in all_accessible_cards
        if hasattr(card, 'access_config') and 
           hasattr(card.access_config, 'allowed_groups') and
           any(str(group_id) in target_groups for group_id in card.access_config.allowed_groups)
    ]
    
    return filtered_cards

@router.get("/{card_id}", response_model=CardsRead)
def get_card_by_id(
    card_id: str = Path(..., description="Unique identifier of the card"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Returns a card by its ID if accessible to the user.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    cards = cards_service.get_accessible_resources(user_id, filters={"id": card_id})
    if not cards:
        raise HTTPException(status_code=404, detail="Not found or no access")
    return cards[0]
