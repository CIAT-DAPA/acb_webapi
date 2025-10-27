from fastapi import Body
from fastapi import APIRouter, HTTPException, Depends, Path, Query
from typing import List
from bson import ObjectId
from services.templates_master_service import TemplatesMasterService
from acb_orm.schemas.templates_master_schema import TemplatesMasterCreate, TemplatesMasterUpdate, TemplatesMasterRead
from acb_orm.schemas.templates_version_schema import TemplatesVersionRead, TemplatesVersionCreate, TemplatesVersionUpdate
from services.templates_version_service import TemplatesVersionService
from acb_orm.enums.status_template import StatusTemplate
from schemas.response_models import TemplateWithCurrentVersion

from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from auth.access_utils import get_current_user, user_has_permission
from tools.logger import logger

router = APIRouter(prefix="/templates", tags=["Template Management"])
service_template = TemplatesMasterService()
service_template_version = TemplatesVersionService()
security = HTTPBearer()

@router.post("/", response_model=TemplatesMasterRead)
def create_template(
    template: TemplatesMasterCreate = ...,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Create a new template master document.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    return service_template.create(template, user_id, 'template_management')

@router.put("/{template_id}", response_model=TemplatesMasterRead)
def update_template(
    template_id: str = Path(..., description="Unique identifier of the template master document to update."),
    template: TemplatesMasterUpdate = ...,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Update an existing template master document by ID. Permission checks and log update are performed.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    return service_template.update(template_id, template, user_id, 'template_management')

# @router.delete("/{template_id}")
# def delete_template(
#     template_id: str = Path(..., description="Unique identifier of the template master document to delete."),
#     credentials: HTTPAuthorizationCredentials = Depends(security)
# ):
#     """
#     Deletes a template master document by its unique ID.
#     """
#     user = get_current_user(credentials)
#     user_id = user["user_db"]["id"]
#     # Obtener el template actual para verificar access_config
#     if not ObjectId.is_valid(template_id):
#         raise HTTPException(status_code=400, detail="Invalid template ID format")
#     obj = TemplatesMaster.objects(id=template_id).first()
#     if not obj:
#         raise HTTPException(status_code=404, detail="Template not found")
#     access_type = obj.access_config.access_type
#     object_dict = obj.to_mongo().to_dict()
#     if access_type != "public":
#         allowed_groups = object_dict.get('access_config', {}).get('allowed_groups', [])
#         for group_id in allowed_groups:
#             if not user_has_permission(user_id, str(group_id), "template_management", "u"):
#                 raise HTTPException(status_code=403, detail=f"User does not have permission to update templates in group {group_id}.")
#     service_template.delete(template_id)
#     return {"success": True}

@router.get("/", response_model=List[TemplatesMasterRead])
def get_all_templates(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Return all templates accessible to the current user.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    return service_template.get_accessible_resources(user_id)

@router.get("/name/{name}", response_model=List[TemplatesMasterRead])
def get_templates_by_name(
    name: str = Path(..., description="Template name or substring to search for."),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    filters = {"template_name__icontains": name}
    return service_template.get_accessible_resources(user_id, filters)

@router.get("/status/{status}", response_model=List[TemplatesMasterRead])
def get_templates_by_status(
    status: str = Path(
        ...,
        description=f"Template status. Possible options: {list(StatusTemplate._value2member_map_.keys())}"
    ),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    # Validar que el status sea uno de los permitidos
    if status not in StatusTemplate._value2member_map_:
        allowed = list(StatusTemplate._value2member_map_.keys())
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}. Allowed: {allowed}")
    filters = {"status": status}
    return service_template.get_accessible_resources(user_id, filters)

@router.get("/{template_id}", response_model=TemplatesMasterRead)
def get_template_by_id(
    template_id: str = Path(..., description="Unique identifier of the template master document."),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Returns a template by its unique ID if accessible to the user.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    templates = service_template.get_accessible_resources(user_id, filters={"id": template_id})
    if not templates:
        raise HTTPException(status_code=404, detail="Not found or no access")
    return templates[0]

@router.get("/{template_id}/current-version", response_model=TemplateWithCurrentVersion)
def get_current_version(
    template_id: str = Path(..., description="Unique identifier of the template master document."),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Returns the template master and its current version by template ID, validating user access.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    
    templates = service_template.get_accessible_resources(user_id, filters={"id": template_id})
    if not templates:
        raise HTTPException(status_code=404, detail="Not found or no access")
    
    template_master = templates[0]
    
    version_id = service_template.get_current_version_id(template_id)
    if not version_id:
        raise HTTPException(status_code=404, detail="No current version found")
    
    try:
        current_version = service_template_version.read_schema.model_validate(service_template_version._serialize_document(version_id))
    except Exception as e:
        logger.error(f"Error retrieving current version: {e}")
        raise HTTPException(status_code=500)
    
    return TemplateWithCurrentVersion(
        master=template_master,
        current_version=current_version
    )

@router.post("/versions", response_model=TemplatesVersionRead)
def create_template_version(
    version: TemplatesVersionCreate = ...,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Creates a new version for a template and updates the master with the new current_version_id.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]

    # Validar acceso al template master usando filtro por id
    templates = service_template.get_accessible_resources(user_id, filters={"id": version.template_master_id})
    if not templates:
        raise HTTPException(status_code=404, detail="Not found or no access")
    
    # Si el template master tiene una versión actual, asignarla como previous_version_id en la nueva versión
    template_master = templates[0]
    previous_version_id = getattr(template_master, "current_version_id", None)
    version_data = version.model_dump()
    if previous_version_id:
        version_data["previous_version_id"] = previous_version_id
        previous_num =  service_template_version.get_by_id(str(previous_version_id)).version_num
        version_data["version_num"] = previous_num + 1
    else:
        version_data["version_num"] = 1
    # Crear la versión con el previous_version_id correcto
    version_obj = service_template_version.create(TemplatesVersionCreate(**version_data), user_id)
    # Actualizar el master con el nuevo current_version_id
    update_data = TemplatesMasterUpdate(current_version_id=str(version_obj.id))
    service_template.update(version.template_master_id, update_data, user_id)
    return version_obj

@router.post("/{template_id}/clone", response_model=TemplatesMasterRead)
def clone_template(
    template_id: str = Path(..., description="ID of the template master to clone"),
    template_name: str = Body(None, description="New name for the cloned template"),
    description: str = Body(None, description="New description for the cloned template"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Clones an existing template. If name/description are provided, clones the master and its current version.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]

    templates = service_template.get_accessible_resources(user_id, filters={"id": template_id})
    if not templates:
        raise HTTPException(status_code=404, detail="Not found or no access")
    template_master = templates[0]
    allowed_groups = template_master.access_config.allowed_groups if hasattr(template_master.access_config, "allowed_groups") else []
    for group_id in allowed_groups:
        if not user_has_permission(user_id, str(group_id), "template_management", "c"):
            raise HTTPException(status_code=403, detail=f"User does not have permission to clone templates in group {group_id}.")

    cloned_master, cloned_version = service_template.clone_master_with_version(
        template_master,
        user_id,
        template_name=template_name,
        description=description
    )
    return cloned_master
  
@router.get("/{template_id}/history", response_model=List[TemplatesVersionRead])
def get_template_history(
    template_id: str = Path(..., description="Unique identifier of the template master document."),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Returns the version history for a template, ordered from most recent to oldest.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    # Validar acceso al template master
    templates = service_template.get_accessible_resources(user_id, filters={"id": template_id})
    if not templates:
        raise HTTPException(status_code=404, detail="Not found or no access")
    # Obtener historial de versiones
    history = service_template_version.get_by_template_id(template_id)
    return history