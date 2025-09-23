from typing import Type, List, Optional, Callable, Any, Dict, Generic, TypeVar
from pydantic import BaseModel, Field
from pydantic.generics import GenericModel

T = TypeVar("T")

class PaginatedResponse(GenericModel, Generic[T]):
    total: int = Field(..., description="Total number of records.")
    limit: int = Field(..., description="Maximum number of records per page.")
    skip: int = Field(..., description="Number of skipped records.")
    page: int = Field(..., description="Current page number.")
    total_pages: int = Field(..., description="Total number of pages.")
    has_next: bool = Field(..., description="Indicates if there is a next page.")
    results: List[T] = Field(..., description="List of results for the current page.")

def build_paginated_response(
    base_query,
    schema_model: Type[BaseModel],
    page: int = 1,
    limit: int = 10,
    skip: Optional[int] = None,
    order_by_fields: Optional[List[str]] = None,
    serialize_fn: Optional[Callable[[Any], Dict]] = None,
):
    """
    Builds a generic paginated response from a MongoEngine query.

    Parameters:
    - base_query: MongoEngine QuerySet object.
    - schema_model: Pydantic model class used for output serialization.
    - page: Page number to retrieve (ignored if `skip` is provided).
    - limit: Max number of records per page.
    - skip: Number of records to skip (overrides `page` if provided).
    - order_by_fields: Optional list of fields to order by (MongoEngine syntax).
    - serialize_fn: Optional function to serialize each document. If not provided,
      the `schema_model` will be used to convert the raw Mongo document.

    Returns:
    A dictionary with pagination metadata and serialized results,
    ready to be returned as JSON.
    """
    total = base_query.count()
    offset = skip if skip is not None else (page - 1) * limit
    total_pages = (total + limit - 1) // limit
    has_next = (offset + limit) < total
    real_page = page if skip is None else (offset // limit) + 1

    if order_by_fields:
        base_query = base_query.order_by(*order_by_fields).collation({'locale': 'es', 'strength': 1})

    results = base_query.skip(offset).limit(limit)

    items = []
    for obj in results:
        if serialize_fn:
            items.append(serialize_fn(obj))
        else:
            data = obj.to_mongo().to_dict()
            data["id"] = str(obj.id)
            items.append(schema_model(**data))

    return {
        "total": total,
        "limit": limit,
        "skip": offset,
        "page": real_page,
        "total_pages": total_pages,
        "has_next": has_next,
        "results": items
    }
