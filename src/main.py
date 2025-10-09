from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo.errors import ServerSelectionTimeoutError
from database import init_db
from dotenv import load_dotenv
from tools.logger import logger
from auth.auth import router as auth_router
from auth.get_client_token import router as get_client_token_router
from auth.token_validation_router import router as validate_token_router
from api.templates_management import router as templates_master_router
from api.roles_management import router as roles_router
from api.groups_management import router as groups_router
from api.bulletins_management import router as bulletins_router
from api.visual_resources_management import router as visual_resources_router
from api.cards_management import router as cards_router
from api.users_management import router as users_router

app = FastAPI(
    title="Bulletin Builder API"
)

load_dotenv()

try:
    init_db()
    logger.info("Conexión a MongoDB exitosa")
except ServerSelectionTimeoutError as e:
    logger.exception("No se pudo conectar con MongoDB al iniciar")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", include_in_schema=False )
def read_root():
    return {"message": "Bulletin Builder API is running!"}


@app.exception_handler(ServerSelectionTimeoutError)
async def db_connection_error_handler(request: Request, exc: ServerSelectionTimeoutError):
    return JSONResponse(
        status_code=503,
        content={"detail": "Error de conexión con la base de datos. Verifica si el servidor está en línea."},
    )


# Auth
app.include_router(auth_router)
app.include_router(get_client_token_router)
app.include_router(validate_token_router)


# Templates Master
app.include_router(templates_master_router)

# Roles
app.include_router(roles_router)

# Groups
app.include_router(groups_router)

# Bulletins
app.include_router(bulletins_router)

# Visual Resources
app.include_router(visual_resources_router)

# Cards
app.include_router(cards_router)

# Users
app.include_router(users_router)

# uvicorn main:app --reload