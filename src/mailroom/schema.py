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
    """
    CREATE TABLE sync_state (
        provider TEXT NOT NULL CHECK (provider IN ('gmail', 'outlook', 'yahoo')),
        account TEXT NOT NULL,
        bookmark TEXT NOT NULL,
        synced_at TEXT NOT NULL,
        PRIMARY KEY (provider, account)
    ) STRICT;
    """,
    """
    CREATE TABLE senders (
        address TEXT PRIMARY KEY,
        status TEXT NOT NULL CHECK (status IN ('trusted', 'muted'))
    ) STRICT;
    """,
    """
    CREATE TABLE triage (
        provider TEXT NOT NULL,
        message_id TEXT NOT NULL,
        outcome TEXT NOT NULL CHECK (outcome IN ('dropped', 'extracted', 'rejected')),
        reason TEXT NOT NULL,
        trusted INTEGER NOT NULL CHECK (trusted IN (0, 1)),
        verified INTEGER NOT NULL CHECK (verified IN (0, 1)),
        bulk INTEGER NOT NULL CHECK (bulk IN (0, 1)),
        notify INTEGER NOT NULL CHECK (notify IN (0, 1)),
        extraction TEXT,
        decided_at TEXT NOT NULL,
        text_cleared_at TEXT,
        PRIMARY KEY (provider, message_id),
        CHECK ((outcome = 'rejected') = (reason != '')),
        CHECK (outcome != 'dropped' OR notify = 0),
        CHECK (outcome = 'extracted' OR (extraction IS NULL AND text_cleared_at IS NULL)),
        CHECK (outcome != 'extracted' OR ((extraction IS NULL) = (text_cleared_at IS NOT NULL)))
    ) STRICT;
    """,
    """
    CREATE TABLE posts (
        item_id TEXT PRIMARY KEY,
        provider TEXT NOT NULL,
        message_id TEXT NOT NULL,
        queued_at TEXT NOT NULL,
        discord_message_id TEXT,
        posted_at TEXT,
        UNIQUE (provider, message_id),
        CHECK ((discord_message_id IS NULL) = (posted_at IS NULL))
    ) STRICT;
    """,
    """
    CREATE TABLE answers (
        item_id TEXT PRIMARY KEY,
        answer TEXT NOT NULL CHECK (answer IN ('yes', 'edit', 'notask', 'mute')),
        title TEXT NOT NULL,
        answered_at TEXT NOT NULL,
        CHECK ((answer IN ('yes', 'edit')) = (title != ''))
    ) STRICT;
    """,
    """
    CREATE TABLE problems (
        key TEXT PRIMARY KEY,
        since TEXT NOT NULL,
        alerted INTEGER NOT NULL CHECK (alerted IN (0, 1))
    ) STRICT;
    CREATE TABLE alerts (
        alert_id TEXT PRIMARY KEY,
        key TEXT NOT NULL UNIQUE,
        text TEXT NOT NULL,
        ping INTEGER NOT NULL CHECK (ping IN (0, 1)),
        queued_at TEXT NOT NULL,
        discord_message_id TEXT,
        posted_at TEXT,
        CHECK ((discord_message_id IS NULL) = (posted_at IS NULL))
    ) STRICT;
    """,
    # 8: the proposed deadline (kept after the text is cleared) and the clearly-dated decision.
    # A column's CHECK may name only columns that already exist, so the order matters.
    """
    ALTER TABLE triage ADD COLUMN deadline_date TEXT
        CHECK (
            deadline_date IS NULL
            OR (outcome = 'extracted' AND date(deadline_date) IS deadline_date)
        );
    ALTER TABLE triage ADD COLUMN deadline_time TEXT
        CHECK (
            deadline_time IS NULL
            OR (deadline_date IS NOT NULL AND strftime('%H:%M', deadline_time) IS deadline_time)
        );
    ALTER TABLE triage ADD COLUMN dated INTEGER NOT NULL DEFAULT 0
        CHECK (
            dated IN (0, 1)
            AND (dated = 0 OR (outcome = 'extracted' AND deadline_date IS NOT NULL))
        );
    """,
)

SCHEMA_VERSION = len(MIGRATIONS)
