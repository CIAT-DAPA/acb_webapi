from pydantic import BaseModel
from acb_orm.schemas.templates_master_schema import TemplatesMasterRead
from acb_orm.schemas.templates_version_schema import TemplatesVersionRead
from acb_orm.schemas.bulletins_master_schema import BulletinsMasterRead
from acb_orm.schemas.bulletins_version_schema import BulletinsVersionRead

class TemplateWithCurrentVersion(BaseModel):
    """Response model for template master with its current version."""
    template_master: TemplatesMasterRead
    current_version: TemplatesVersionRead

class BulletinWithCurrentVersion(BaseModel):
    """Response model for bulletin master with its current version."""
    bulletin_master: BulletinsMasterRead
    current_version: BulletinsVersionRead