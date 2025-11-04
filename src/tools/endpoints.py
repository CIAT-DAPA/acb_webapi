import re
from fastapi import Query, HTTPException
from typing import List, Callable, Any, Dict, Optional, Type
from bson import ObjectId
from pydantic import BaseModel

def get_pretty_name(collection) -> str:
    """Devuelve el nombre bonito como 'Adm 2' para Adm2"""
    return re.sub(r'(?<!^)(?=[A-Z])', ' ', collection.__name__).title()


def get_all_factory(collection, schema_model: Type[BaseModel], serialize_fn: Callable[[Any], Dict]):
    pretty_name = get_pretty_name(collection)

    async def get_all(response_model=List[schema_model]):
        """
        Get all {pretty_name} records.
        """
        records = collection.objects().limit(1000)
        return [serialize_fn(r) for r in records]

    get_all.__name__ = f"get_all_{collection.__name__.lower()}"
    get_all.__doc__ = f"Get all {pretty_name} records."
    return get_all


def get_by_ids_factory(collection, schema_model: Type[BaseModel], serialize_fn: Callable[[Any], Dict]):
    pretty_name = get_pretty_name(collection)

    async def get_by_ids(
        ids: str = Query(..., description=f"Lista de ObjectId válidos separados por coma. Ejemplo: ?ids=665f...,...")
    ):
        """
        Obtener múltiples registros {pretty_name} por sus MongoDB ObjectIds.
        """
        search_ids = [id.strip() for id in ids.split(",") if id.strip()]
        invalid_ids = [i for i in search_ids if not ObjectId.is_valid(i)]
        if invalid_ids:
            raise HTTPException(
                status_code=400,
                detail=f"IDs no válidos: {', '.join(invalid_ids)}"
            )
        matches = collection.objects(id__in=search_ids)
        return [serialize_fn(m) for m in matches]

    get_by_ids.__name__ = f"get_{collection.__name__.lower()}_by_ids"
    get_by_ids.__doc__ = f"Obtener múltiples registros {pretty_name} por sus MongoDB ObjectIds."
    return get_by_ids


def get_by_name_factory(collection, schema_model: Type[BaseModel], serialize_fn: Callable[[Any], Dict]):
    pretty_name = get_pretty_name(collection)

    async def get_by_name(
        name_param: str = Query(..., description=f"Uno o más nombres separados por coma para búsqueda parcial sin distinción de mayúsculas")
    ):
        """
        Obtener registros {pretty_name} que coincidan parcialmente con uno o más nombres.
        Ejemplo: /{collection.__name__.lower()}/by-name?name=Cali,Palmira
        """
        search_terms = [term.strip() for term in name_param.split(",") if term.strip()]
        safe_terms = [re.escape(term) for term in search_terms]
        query = {"$or": [{"name": {"$regex": term, "$options": "i"}} for term in safe_terms]}
        matches = collection.objects(__raw__=query)
        return [serialize_fn(m) for m in matches]

    get_by_name.__name__ = f"get_{collection.__name__.lower()}_by_name"
    get_by_name.__doc__ = f"Obtener registros {pretty_name} que coincidan parcialmente con uno o más nombres."
    return get_by_name