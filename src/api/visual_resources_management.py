from fastapi import APIRouter, HTTPException, Depends, Path, Body
from typing import List
from services.visual_resources_service import VisualResourcesService
from acb_orm.schemas.visual_resources_schema import VisualResourcesCreate, VisualResourcesUpdate, VisualResourcesRead
from acb_orm.enums.status_visual_resource import StatusVisualResource
from acb_orm.enums.file_type import FileType
from auth.access_utils import get_current_user, user_has_permission
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

router = APIRouter(prefix="/visual-resources", tags=["Visual Resources"])
visual_resources_service = VisualResourcesService()
security = HTTPBearer()

@router.post("/", response_model=VisualResourcesRead)
def create_visual_resource(
    resource: VisualResourcesCreate = ..., 
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Create a new visual resource document.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    return visual_resources_service.create(resource, user_id, 'templates_management')

@router.put("/{resource_id}", response_model=VisualResourcesRead)
def update_visual_resource(
    resource_id: str = Path(..., description="ID of the visual resource to update"),
    resource: VisualResourcesUpdate = ..., 
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Update a visual resource by its ID. Permission checks and log updates are applied.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    return visual_resources_service.update(resource_id, resource, user_id, 'templates_management')

@router.get("/", response_model=List[VisualResourcesRead])
def get_all_visual_resources(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Return all visual resources accessible to the current user.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    return visual_resources_service.get_accessible_resources(user_id)

@router.get("/name/{name}", response_model=List[VisualResourcesRead])
def get_visual_resources_by_name(
    name: str = Path(..., description="Name or substring of the visual resource"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Returns visual resources whose name contains the given substring (case-insensitive).
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    filters = {"file_name__icontains": name}
    return visual_resources_service.get_accessible_resources(user_id, filters)

@router.get("/status/{status}", response_model=List[VisualResourcesRead])
def get_visual_resources_by_status(
    status: str = Path(..., description=f"Status. Possible options: {list(StatusVisualResource._value2member_map_.keys())}"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Returns visual resources by status, validating against allowed values.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    if status not in StatusVisualResource._value2member_map_:
        allowed = list(StatusVisualResource._value2member_map_.keys())
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}. Allowed: {allowed}")
    filters = {"status": status}
    return visual_resources_service.get_accessible_resources(user_id, filters)

@router.get("/type/{file_type}", response_model=List[VisualResourcesRead])
def get_visual_resources_by_file_type(
    file_type: str = Path(..., description=f"File type. Possible options: {list(FileType._value2member_map_.keys())}"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Returns visual resources by file type, validating against allowed values.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    if file_type not in FileType._value2member_map_:
        allowed = list(FileType._value2member_map_.keys())
        raise HTTPException(status_code=400, detail=f"Invalid file type: {file_type}. Allowed: {allowed}")
    filters = {"file_type": file_type}
    return visual_resources_service.get_accessible_resources(user_id, filters)

@router.get("/{resource_id}", response_model=VisualResourcesRead)
def get_visual_resource_by_id(
    resource_id: str = Path(..., description="ID of the visual resource"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Returns a visual resource by its ID if accessible to the user.
    """
    user = get_current_user(credentials)
    user_id = user["user_db"]["id"]
    resources = visual_resources_service.get_accessible_resources(user_id, filters={"id": resource_id})
    if not resources:
        raise HTTPException(status_code=404, detail="Not found or no access")
    return resources[0]
