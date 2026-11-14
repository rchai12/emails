"""What the tasks app receives for a follow-up, and which task ids may name a path."""

from datetime import UTC, datetime

import pytest

from mailroom.store import Link
from mailroom.tasks_app import is_task_id, link_payload

NOW = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
LINK = Link("b" * 32, "gmail", "personal/m2", "a" * 32, "task-1", NOW, None)


def test_the_link_names_only_the_follow_up_email() -> None:
    assert link_payload(LINK, "https://mail.google.com/mail/#all/m2") == {
        "source": "email",
        "provider": "gmail",
        "message_id": "personal/m2",
        "link": "https://mail.google.com/mail/#all/m2",
    }


@pytest.mark.parametrize(
    ("task_id", "valid"),
    [
        ("task-1", True),
        ("abc_DEF-9", True),
        ("x" * 100, True),
        ("", False),
        ("x" * 101, False),
        (".", False),
        ("..", False),
        ("a.b", False),
        ("a/b", False),
        ("task 1", False),
        ("task-1\n", False),
        ("tâche", False),
        ("task-٣", False),
    ],
    ids=[
        "plain",
        "mixed",
        "longest",
        "empty",
        "too-long",
        "dot",
        "dot-dot",
        "inner-dot",
        "slash",
        "space",
        "newline",
        "accent",
        "arabic-digit",
    ],
)
def test_a_task_id_is_ascii_letters_digits_dash_and_underscore(task_id: str, valid: bool) -> None:
    assert is_task_id(task_id) is valid
