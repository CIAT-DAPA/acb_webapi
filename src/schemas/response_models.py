from typing import Dict
from pydantic import BaseModel
from acb_orm.schemas.templates_master_schema import TemplatesMasterRead
from acb_orm.schemas.templates_version_schema import TemplatesVersionRead
from acb_orm.schemas.bulletins_master_schema import BulletinsMasterRead
from acb_orm.schemas.bulletins_version_schema import BulletinsVersionRead
from acb_orm.schemas.cards_schema import CardsRead

class TemplateWithCurrentVersion(BaseModel):
    """Response model for template master with its current version."""
    master: TemplatesMasterRead
    current_version: TemplatesVersionRead

class BulletinWithCurrentVersion(BaseModel):
    """Response model for bulletin master with its current version."""
    master: BulletinsMasterRead
    current_version: BulletinsVersionRead

class BulletinWithCurrentVersionPublic(BaseModel):
    """Public response model with embedded cards metadata."""
    master: BulletinsMasterRead
    current_version: BulletinsVersionRead
    cards_metadata: Dict[str, CardsRead]