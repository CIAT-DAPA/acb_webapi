from fastapi import APIRouter, Depends, Query, Response, HTTPException
from typing import List, Optional, Dict, Any
import acb_orm.enums as orm_enums
from auth.access_utils import get_current_user

router = APIRouter(prefix="/meta", tags=["Meta"])


@router.get("/enums")
def list_enums(response: Response,
               names: Optional[str] = Query(None, description="Comma-separated enum class names to fetch"),
               include_labels: bool = Query(False, description="Include human-friendly labels for values")):
    """
    Returns enum definitions from the ORM.

    If `names` is omitted, returns all enums. `names` may be a comma-separated list of enum class names.
    By default returns the raw values; if `include_labels=true` the API will add a `label` generated
    from the value (title-cased). The ORM currently supplies values only; labels/locale can be
    added later to the ORM as metadata.
    """
    try:
        if names:
            requested = [n.strip() for n in names.split(",") if n.strip()]
            enums: Dict[str, List[Any]] = {}
            for n in requested:
                vals = orm_enums.get_enum(n)
                if vals is None:
                    # If a requested enum is not found, return 404
                    raise HTTPException(status_code=404, detail=f"Enum '{n}' not found")
                enums[n] = vals
        else:
            enums = orm_enums.get_all_enums()

        # Optionally add labels
        if include_labels:
            def with_label(vals):
                return [{"value": str(v), "label": str(v).replace("_", " ").title()} for v in vals]

            enums = {k: with_label(v) for k, v in enums.items()}

        # Add caching headers (these lists change rarely)
        response.headers["Cache-Control"] = "public, max-age=3600"

        return {"enums": enums}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error listing enums: {str(e)}")
