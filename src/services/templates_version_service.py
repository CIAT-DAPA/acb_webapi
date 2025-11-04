from typing import List, Any
from bson import ObjectId
from acb_orm.collections.templates_version import TemplatesVersion
from acb_orm.schemas.templates_version_schema import TemplatesVersionCreate, TemplatesVersionUpdate, TemplatesVersionRead
from auth.access_utils import serialize_log
from .base_service import BaseService

class TemplatesVersionService(
    BaseService[
        TemplatesVersion,
        TemplatesVersionCreate,
        TemplatesVersionRead,
        TemplatesVersionUpdate
    ]
):

    @staticmethod
    def _serialize_document(document) -> dict:
        """
        Recibe un documento MongoEngine y lo convierte a dict, serializando los ObjectId relevantes.
        """
        data = document.to_mongo().to_dict()
        if '_id' in data:
            data['id'] = str(data['_id'])
        if 'template_master_id' in data and isinstance(data['template_master_id'], ObjectId):
            data['template_master_id'] = str(data['template_master_id'])
        if 'previous_version_id' in data and isinstance(data['previous_version_id'], ObjectId):
            data['previous_version_id'] = str(data['previous_version_id'])
        if 'log' in data:
            data['log'] = serialize_log(document.log)
        return data


    def __init__(self):
        super().__init__(TemplatesVersion, TemplatesVersionRead)
    
    def get_by_template_id(self, template_id: str) -> List[TemplatesVersionRead]:
        """
        Returns all versions for a given template_id, ordered by creation date (most recent first).
        """
        objs = self.model.objects(template_master_id=template_id).order_by('-log__created_at')
        return [self.read_schema.model_validate(self._serialize_document(obj)) for obj in objs]
    
    def clone_current_version(self, template_master, user_id: str):
        """
        Clona la versión actual del template master.
        """
        current_version_id = getattr(template_master, "current_version_id", None)
        if not current_version_id:
            raise Exception("No current version to clone")
        current_version = self.get_by_id(str(current_version_id))
        return self.clone_version(current_version, template_master.id, user_id)

    def clone_version(self, version: TemplatesVersionRead, new_template_master_id: str, user_id: str):
        """
        Clona una versión, asignando el nuevo template_master_id
        """
        version_data = version.model_dump()
        version_data.pop("id", None)
        version_data["template_master_id"] = new_template_master_id
        version_data["previous_version_id"] = None
         
        original_template_id = version.template_master_id if hasattr(version, "template_master_id") else None
        original_version_id = getattr(version, "id", None)
        version_data["commit_message"] = f"Cloned from template {original_template_id}, original version {original_version_id}"
        return self.create(TemplatesVersionCreate(**version_data), user_id)