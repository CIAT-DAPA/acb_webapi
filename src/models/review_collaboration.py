from mongoengine import (
    DateTimeField,
    Document,
    IntField,
    ObjectIdField,
    StringField,
)


class ReviewSession(Document):
    """Temporary presence session for one browser tab reviewing a bulletin."""

    meta = {
        "collection": "review_sessions",
        "indexes": [
            "bulletin_master_id",
            "user_id",
            {"fields": ["session_id"], "unique": True},
            # MongoDB TTL cleanup. The API also filters sessions using a shorter
            # active window because the TTL monitor does not run continuously.
            {"fields": ["last_seen_at"], "expireAfterSeconds": 90},
        ],
    }

    bulletin_master_id = ObjectIdField(required=True)
    session_id = StringField(required=True)
    user_id = ObjectIdField(required=True)
    user_first_name = StringField()
    user_last_name = StringField()
    entered_at = DateTimeField(required=True)
    last_seen_at = DateTimeField(required=True)


class ReviewDecision(Document):
    """Persistent final decision metadata for one bulletin review cycle."""

    meta = {
        "collection": "review_decisions",
        "indexes": [
            "bulletin_master_id",
            "decided_by",
            {
                "fields": ["bulletin_master_id", "cycle_number"],
                "unique": True,
            },
        ],
    }

    bulletin_master_id = ObjectIdField(required=True)
    cycle_number = IntField(required=True)
    action = StringField(required=True, choices=("approved", "rejected"))
    target_status = StringField(required=True)
    decided_by = ObjectIdField(required=True)
    decided_by_first_name = StringField()
    decided_by_last_name = StringField()
    decided_at = DateTimeField(required=True)