from mongoengine import connect
import tools.config as config

DATABASE_URL = config.DATABASE_URL
DATABASE_NAME = config.DATABASE_NAME

def init_db():
    conn = connect(
        db=DATABASE_NAME,
        host=DATABASE_URL,
        alias="default"
    )

    conn.admin.command("ping")