from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

router = APIRouter()

@router.get("/", include_in_schema=False)
async def root(request: Request):
    """
    Redirect to /docs if accessed from a browser, otherwise return API info
    """
    user_agent = request.headers.get("user-agent", "").lower()
    
    # Check if request comes from a browser
    browser_indicators = ["mozilla", "chrome", "safari", "edge", "firefox", "opera"]
    is_browser = any(indicator in user_agent for indicator in browser_indicators)
    
    if is_browser:
        return RedirectResponse(url="/docs")
    else:
        # Return API info for programmatic access
        return {
            "message": "Bulletin Builder API",
            "version": "1.0",
            "description": "API for Bulletin Builder.",
            "docs": "/docs"
        }