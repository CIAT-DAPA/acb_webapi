from mongoengine import connect
from dotenv import load_dotenv
import os

load_dotenv()


DATABASE_URL = os.getenv("DATABASE_URL")
DATABASE_NAME = os.getenv("DATABASE_NAME")

def init_db():
    conn = connect(
        db=DATABASE_NAME,
        host=DATABASE_URL,
        alias="default"
    )

    conn.admin.command("ping")