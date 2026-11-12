"""The database schema, as numbered migrations.

`MIGRATIONS[i]` moves a database from `PRAGMA user_version` i to i + 1. A later phase appends to
the tuple; it never edits an earlier entry. Times are text in UTC with microseconds, such as
`2026-11-11T09:00:00.000000+00:00`, so text order is time order.
"""

MIGRATIONS: tuple[str, ...] = (
    """
    CREATE TABLE messages (
        provider TEXT NOT NULL CHECK (provider IN ('gmail', 'outlook', 'yahoo')),
        message_id TEXT NOT NULL,
        thread_id TEXT NOT NULL,
        received_at TEXT NOT NULL,
        link TEXT NOT NULL,
        sender TEXT NOT NULL,
        sender_name TEXT NOT NULL,
        subject TEXT NOT NULL,
        sent_at TEXT,
        list_unsubscribe INTEGER NOT NULL CHECK (list_unsubscribe IN (0, 1)),
        body_text TEXT,
        authentication_results TEXT,
        fetched_at TEXT NOT NULL,
        text_cleared_at TEXT,
        PRIMARY KEY (provider, message_id),
        CHECK (
            (text_cleared_at IS NULL AND body_text IS NOT NULL
                AND authentication_results IS NOT NULL)
            OR (text_cleared_at IS NOT NULL AND body_text IS NULL
                AND authentication_results IS NULL)
        )
    ) STRICT;
    CREATE INDEX messages_text_expiry ON messages (fetched_at) WHERE text_cleared_at IS NULL;
    """,
)

SCHEMA_VERSION = len(MIGRATIONS)
