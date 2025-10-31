from typing import List, Any, Optional
from bson import ObjectId
from fastapi import HTTPException
from acb_orm.collections.cards import Cards
from acb_orm.schemas.cards_schema import CardsCreate, CardsUpdate, CardsRead
from mongoengine import Document, DoesNotExist
from auth.access_utils import serialize_log
from tools.logger import logger
from tools.utils import parse_object_ids
from .base_service import BaseService

class CardsService(
    BaseService[
        Cards,
        CardsCreate,
        CardsRead,
        CardsUpdate
    ]
):
    @staticmethod
    def _serialize_document(document) -> dict:
        data = document.to_mongo().to_dict()
        if '_id' in data:
            data['id'] = str(data['_id'])
        if 'log' in data:
            data['log'] = serialize_log(document.log)
        if 'templates_master_ids' in data and isinstance(data['templates_master_ids'], list):
            data['templates_master_ids'] = [str(t) if isinstance(t, ObjectId) else t for t in data['templates_master_ids']]
        if 'access_config' in data and isinstance(data['access_config'], dict):
            if 'allowed_groups' in data['access_config'] and isinstance(data['access_config']['allowed_groups'], list):
                data['access_config']['allowed_groups'] = [str(g) if isinstance(g, ObjectId) else g for g in data['access_config']['allowed_groups']]
        return data

    def __init__(self):
        super().__init__(Cards, CardsRead)

    def get_by_name(self, name: str) -> List[CardsRead]:
        objs = Cards.objects(card_name__icontains=name)
        return [self.read_schema.model_validate(self._serialize_document(obj)) for obj in objs]

    def get_by_type(self, card_type: str) -> List[CardsRead]:
        objs = Cards.objects(card_type=card_type)
        return [self.read_schema.model_validate(self._serialize_document(obj)) for obj in objs]

    def get_by_template_master_id(self, template_master_id: str) -> List[CardsRead]:
        if not ObjectId.is_valid(template_master_id):
            logger.error(f"Invalid template master ID format: {template_master_id}")
            raise HTTPException(status_code=400, detail="Invalid template master ID format")
        objs = Cards.objects(templates_master_ids=ObjectId(template_master_id))
        return [self.read_schema.model_validate(self._serialize_document(obj)) for obj in objs]

    def get_by_id(self, card_id: str) -> CardsRead:
        if not ObjectId.is_valid(card_id):
            logger.error(f"Invalid card ID format: {card_id}")
            raise HTTPException(status_code=400, detail="Invalid card ID format")
        obj = Cards.objects(id=card_id).first()
        if not obj:
            raise HTTPException(status_code=404, detail="Card not found")
        return self.read_schema.model_validate(self._serialize_document(obj))

    def clone_card(self, card: CardsRead, user_id: str, card_name: Optional[str] = None, description: Optional[str] = None) -> CardsRead:
        """
        Clones a card with optional custom name and description.
        """
        card_data = card.model_dump()
        card_data.pop("id", None)
        card_data["card_name"] = card_name or card_data["card_name"] + " (clon)"
        if description:
            card_data["description"] = description

        new_card = self.create(CardsCreate(**card_data), user_id)
        return new_card
