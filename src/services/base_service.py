from typing import TypeVar, Generic, Type, Optional, Any, Dict, List
from pydantic import BaseModel, ValidationError
from mongoengine import Document, DoesNotExist, ValidationError as MongoValidationError, NotUniqueError
from mongoengine.fields import ReferenceField
from bson import ObjectId
from acb_orm.schemas.log_schema import LogUpdate, LogCreate


from auth.access_utils import get_user_groups, user_has_permission, is_superadmin
from tools.logger import logger
from tools.utils import parse_object_ids
from fastapi import HTTPException

ModelType = TypeVar("ModelType", bound=Document)
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
ReadSchemaType = TypeVar("ReadSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)


class BaseService(Generic[ModelType, CreateSchemaType, ReadSchemaType, UpdateSchemaType]):
    def __init__(self, model: Type[ModelType], read_schema: Type[ReadSchemaType]):
        """
        Initializes the base service with the model and read schema.
        :param model: MongoEngine model
        :param read_schema: Pydantic schema for output serialization
        """
        self.model = model
        self.read_schema = read_schema

    def get_accessible_resources(self, user_id: str, filters: Optional[Dict[str, Any]] = None) -> List[ReadSchemaType]:
        """
        Returns resources accessible to the user (public and restricted by group), serialized with the read_schema.
        :param user_id: User ID
        :param filters: Additional filters to apply
        :return: List of serialized resources
        """
        try:
            if is_superadmin(user_id):
                return self.get_all(filters)
            user_groups = get_user_groups(user_id)
            public = self.model.objects(access_config__access_type="public", **(filters or {}))
            restricted = self.model.objects(access_config__access_type="restricted", access_config__allowed_groups__in=user_groups, **(filters or {}))
            all_objs = list(public) + list(restricted)
            return [self.read_schema.model_validate(self._serialize_document(obj)) for obj in all_objs]
        except Exception as e:
            logger.error(f"Error in get_accessible_resources: {e}")
            raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")

    def get_by_id(self, id: str) -> ReadSchemaType:
        """
        Gets a resource by its ID and serializes it with the read_schema.
        :param id: Resource ID
        :return: Serialized resource or None if not found
        """
        try:
            obj = self.model.objects.get(id=id)
            return self.read_schema.model_validate(self._serialize_document(obj))
        except DoesNotExist as e:
            logger.error(f"Resource not found in get_by_id: id={id} - {e}")
            raise HTTPException(status_code=404, detail="Resource not found")
        except Exception as e:
            logger.error(f"Error in get_by_id: {e}")
            raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")
        
    def get_by_ids(self, ids_str: str) -> List[ReadSchemaType]:
        """
        Gets multiple resources by a comma-separated string of IDs, validating all IDs.
        :param ids_str: Comma-separated string of ObjectIds
        :return: List of serialized resources
        """
        try:
            ids = parse_object_ids(ids_str)
            query = self.model.objects(id__in=ids)
            return [self.read_schema.model_validate(self._serialize_document(obj)) for obj in query]
        except HTTPException as e:
            # Re-raise HTTPException for invalid IDs
            raise e
        except Exception as e:
            logger.error(f"Error in get_by_ids: {e}")
            raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")

    def get_all(self, filters: Optional[Dict[str, Any]] = None) -> List[ReadSchemaType]:
        """
        Gets all resources matching the filters and serializes them.
        :param filters: Filter dictionary
        :return: List of serialized resources
        """
        try:
            query = self.model.objects(**(filters or {}))
            return [self.read_schema.model_validate(self._serialize_document(obj)) for obj in query]
        except Exception as e:
            logger.error(f"Error in get_all: {e}")
            raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")

    def create(self, obj_in: CreateSchemaType, user_id: Optional[str] = None, module: Optional[str] = None) -> ReadSchemaType:
        """
        Creates a new resource from the input schema and serializes it.
        If user_id is provided, generates the log automatically.
        :param obj_in: Input schema
        :param user_id: User ID (optional)
        :return: Created and serialized resource
        """
        obj_data = obj_in.model_dump()

        if user_id is not None and "access_config" in self.model._fields and module is not None:
                access_type = obj_data["access_config"].get("access_type")
                if access_type != "public":
                    allowed_groups = obj_data["access_config"].get("allowed_groups", [])
                    # Verificar permisos en todos los grupos requeridos
                    for group_id in allowed_groups:
                        if not user_has_permission(user_id, str(group_id), module, "c"):
                            raise HTTPException(status_code=403, detail=f"User does not have permission to create resource in group {group_id}.")
        try:
            obj_data = obj_in.model_dump()            
            
            if user_id is not None and "log" in self.model._fields:
                obj_data["log"] = LogCreate(creator_user_id=user_id).model_dump()
            
            db_obj = self.model(**obj_data)
            db_obj.save()

            return self.read_schema.model_validate(self._serialize_document(db_obj))
        
        except NotUniqueError as e:
            logger.error(f"Duplicate key error in create: {e}")
            raise HTTPException(status_code=409, detail=f"Duplicate key error: {str(e)}")
        except (ValidationError, MongoValidationError) as e:
            logger.error(f"Validation error in create: {e}")
            raise HTTPException(status_code=400, detail=f"Validation error: {str(e)}")
        except Exception as e:
            logger.error(f"Error in create: {e}")
            raise HTTPException(status_code=500, detail=f"Error creating resource: {str(e)}")

    def update(self, id: str, obj_in: UpdateSchemaType | Dict[str, Any], user_id: Optional[str] = None, module: Optional[str] = None) -> ReadSchemaType:
        """
        Updates a resource by its ID and serializes it.
        If user_id is provided, updates the log automatically.
        :param id: Resource ID
        :param obj_in: Update schema or dictionary
        :param user_id: User ID (optional)
        :return: Updated and serialized resource or None if not found
        """
        if not ObjectId.is_valid(id):
            logger.error(f"Invalid template ID format: {id}")
            raise HTTPException(status_code=400, detail="Invalid template ID format")

        db_obj = self.model.objects.get(id=id)
        update_data = obj_in.model_dump(exclude_unset=True) if isinstance(obj_in, BaseModel) else obj_in
        obj_dict = db_obj.to_mongo().to_dict()

        if user_id is not None and "access_config" in self.model._fields and module is not None:
            access_type = obj_dict["access_config"].get("access_type")
            if access_type != "public":
                allowed_groups = obj_dict["access_config"].get("allowed_groups", [])
                # Verificar permisos en todos los grupos requeridos
                for group_id in allowed_groups:
                    if not user_has_permission(user_id, str(group_id), module, "u"):
                        raise HTTPException(status_code=403, detail=f"User does not have permission to update resource in group {group_id}.")

        try:
            
            if user_id is not None and "log" in self.model._fields:
                # Conservar creator_user_id y created_at del log original (dict)
                original_log = obj_dict.get('log', {})
                log_update = LogUpdate(updater_user_id=user_id).model_dump()
                if original_log:
                    log_update["creator_user_id"] = str(original_log.get("creator_user_id"))
                    log_update["created_at"] = original_log.get("created_at")
                update_data["log"] = log_update
            
            for field_name, field in self.model._fields.items():
                if isinstance(field, ReferenceField) and field_name in update_data:
                    value = update_data[field_name]
                    if isinstance(value, str) and ObjectId.is_valid(value):
                        update_data[field_name] = ObjectId(value)

            db_obj.modify(**update_data)
            db_obj.reload()
            return self.read_schema.model_validate(self._serialize_document(db_obj))
        except DoesNotExist as e:
            logger.error(f"Resource not found in update: id={id} - {e}")
            raise HTTPException(status_code=404, detail="Resource not found")
        except NotUniqueError as e:
            logger.error(f"Duplicate key error in update: {e}")
            raise HTTPException(status_code=409, detail=f"Duplicate key error: {str(e)}")
        except (ValidationError, MongoValidationError) as e:
            logger.error(f"Validation error in update: {e}")
            raise HTTPException(status_code=400, detail=f"Validation error: {str(e)}")
        except Exception as e:
            logger.error(f"Error in update: {e}")
            raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")

    def delete(self, id: str) -> None:
        """
        Deletes a resource by its ID.
        :param id: Resource ID
        :return: True if deleted, False if not found
        """
        try:
            db_obj = self.model.objects.get(id=id)
            db_obj.delete()
        except DoesNotExist as e:
            logger.error(f"Resource not found in delete: id={id} - {e}")
            raise HTTPException(status_code=404, detail="Resource not found")
        except Exception as e:
            logger.error(f"Error in delete: {e}")
            raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")
