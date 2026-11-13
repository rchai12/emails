from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, date, datetime, time

import httpx
import pytest

from mailroom.checkpoint import answered_message, checkpoint2_message
from mailroom.config import Settings, get_settings
from mailroom.discord_post import DiscordUnavailable
from mailroom.extractor import Deadline, Extraction
from mailroom.interactions import handle_interaction
from mailroom.record import Record
from mailroom.store import Answer, Store, Verdict, open_store
from tests.fakes import FakeDiscord
from tests.support import fixed_ids, fixed_times

ITEM = "0123456789abcdef0123456789abcdef"
RECORD = Record(
    provider="gmail",
    message_id="m1",
    thread_id="t1",
    received_at=datetime(2026, 11, 10, 8, 0, tzinfo=UTC),
    link="https://mail.google.com/mail/?authuser=owner@example.test#all/m1",
    sender="billing@example.test",
    sender_name="Billing Team",
    subject="Your November bill",
    sent_at=None,
    body_text="Your bill of $42.00 is due on November 20.\nPay at `portal`.",
    list_unsubscribe=False,
    authentication_results=(),
)
EXTRACTION = Extraction(
    summary="Billing says the November bill of $42.00 is due on November 20.",
    actionable=True,
    urgent=False,
    title="Pay the November bill",
    deadline=Deadline(date(2026, 11, 20), time(17, 0), True, "due on November 20"),
    suspicious=False,
    suspicion_reason="",
    confidence="high",
)
VERDICT = Verdict(
    outcome="extracted",
    trusted=False,
    verified=True,
    bulk=False,
    notify=True,
    extraction=EXTRACTION,
)
CALLBACK = "https://discord.com/api/v10/interactions/{id}/{token}/callback"


def ephemeral(text: str) -> dict:
    return {"type": 4, "data": {"content": text, "flags": 64, "allowed_mentions": {"parse": []}}}


def form(value: str) -> dict:
    text_input = {
        "type": 4,
        "custom_id": "title",
        "style": 1,
        "min_length": 1,
        "max_length": 100,
        "required": True,
        "value": value,
    }
    return {
        "type": 9,
        "data": {
            "custom_id": f"mr:title:{ITEM}",
            "title": "Edit task title",
            "components": [{"type": 18, "label": "Task title", "component": text_input}],
        },
    }


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("MAILROOM_DISCORD_CHANNEL_ID", "111111111111111111")
    monkeypatch.setenv("MAILROOM_DISCORD_OWNER_ID", "444444444444444444")
    return get_settings()


def posted_store(record: Record = RECORD, verdict: Verdict = VERDICT) -> Store:
    store = open_store(get_settings())
    store.add(record)
    store.save_triage("gmail", "m1", verdict)
    store.queue_notified()
    store.mark_posted(ITEM, "1300000000000000001")
    return store


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> Iterator[Store]:
    fixed_ids(monkeypatch, ITEM)
    fixed_times(
        monkeypatch,
        "2026-11-10T08:00:00+00:00",
        "2026-11-10T08:00:01+00:00",
        "2026-11-10T08:01:00+00:00",
        "2026-11-10T08:02:00+00:00",
        "2026-11-10T09:00:00+00:00",
    )
    opened = posted_store()
    yield opened
    opened.close()


def answer(
    store: Store, settings: Settings, discord: FakeDiscord, event: dict
) -> tuple[str, dict | None]:
    http = httpx.Client(transport=httpx.MockTransport(discord.handler))
    before = len(discord.callbacks)
    outcome = handle_interaction(event, store, settings, http)
    replies = discord.callbacks[before:]
    assert len(replies) <= 1
    return outcome, replies[0][1] if replies else None


# Who can answer


@pytest.mark.parametrize(
    "where",
    [{"user_id": "555555555555555555"}, {"channel_id": "999999999999999999"}],
    ids=["another-user", "another-channel"],
)
def test_a_press_from_anyone_else_or_elsewhere_changes_nothing(
    store: Store, settings: Settings, where: dict
) -> None:
    discord = FakeDiscord()
    outcome, reply = answer(store, settings, discord, discord.press(f"mr:mute:{ITEM}", **where))
    assert (outcome, reply) == ("ignored", {"type": 6})
    assert store.answer(ITEM) is None
    assert store.sender_status("billing@example.test") is None


@pytest.mark.parametrize(
    "custom_id",
    ["mr:mute", f"xx:mute:{ITEM}", f"mr:delete:{ITEM}", "mr:mute:ffffffffffffffffffffffffffffffff"],
    ids=["too-few-parts", "other-prefix", "unknown-action", "unknown-item"],
)
def test_a_button_id_that_is_not_ours_changes_nothing(
    store: Store, settings: Settings, custom_id: str
) -> None:
    discord = FakeDiscord()
    assert answer(store, settings, discord, discord.press(custom_id)) == ("ignored", {"type": 6})
    assert store.answer(ITEM) is None


def test_without_an_owner_or_channel_nothing_is_sent(store: Store) -> None:
    discord = FakeDiscord()
    with pytest.raises(DiscordUnavailable) as caught:
        answer(store, get_settings(), discord, discord.press(f"mr:yes:{ITEM}"))
    assert str(caught.value) == "discord unavailable (not configured)"
    assert discord.requests == []


def test_a_slash_command_is_left_for_later(store: Store, settings: Settings) -> None:
    discord = FakeDiscord()
    event = {**discord.press(f"mr:yes:{ITEM}"), "type": 2}
    assert answer(store, settings, discord, event) == ("ignored", None)
    assert discord.requests == []


# Show full text and Trust sender


def test_show_full_text_is_a_private_code_block(store: Store, settings: Settings) -> None:
    discord = FakeDiscord()
    outcome, reply = answer(store, settings, discord, discord.press(f"mr:full:{ITEM}"))
    assert outcome == "full"
    assert reply == ephemeral(
        "```\nYour bill of $42.00 is due on November 20.\nPay at ˋportalˋ.\n```"
    )
    (request,) = discord.requests
    event = discord.callbacks[0][0]
    assert str(request.url) == CALLBACK.format(id=event, token="interaction-token-1")
    assert request.headers["user-agent"] == "DiscordBot (mailroom, 0.1.0)"
    assert "authorization" not in request.headers


def test_a_long_email_is_cut_with_a_note(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    fixed_ids(monkeypatch, ITEM)
    with posted_store(replace(RECORD, body_text="a" * 1901)) as store:
        discord = FakeDiscord()
        _, reply = answer(store, settings, discord, discord.press(f"mr:full:{ITEM}"))
    assert reply == ephemeral(
        "```\n" + "a" * 1900 + "\n```\n"
        "The email is longer than Discord allows; use Open email to read the rest."
    )


def test_expired_text_points_to_the_link(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    fixed_ids(monkeypatch, ITEM)
    fixed_times(
        monkeypatch,
        "2026-11-10T08:00:00+00:00",
        "2026-11-10T08:00:01+00:00",
        "2026-11-10T08:01:00+00:00",
        "2026-11-10T08:02:00+00:00",
        "2026-11-11T08:30:00+00:00",
    )
    with posted_store() as store:
        assert store.clear_expired_text() == 1
        discord = FakeDiscord()
        _, reply = answer(store, settings, discord, discord.press(f"mr:full:{ITEM}"))
    assert reply == ephemeral(
        "The email text was deleted after 24 hours; use Open email to read it."
    )


def test_trust_sender_adds_the_address_without_answering(store: Store, settings: Settings) -> None:
    discord = FakeDiscord()
    outcome, reply = answer(store, settings, discord, discord.press(f"mr:trust:{ITEM}"))
    assert outcome == "trusted"
    assert reply == ephemeral("Added to your trusted senders:\n```\nbilling@example.test\n```")
    assert store.sender_status("billing@example.test") == "trusted"
    assert store.answer(ITEM) is None


@pytest.mark.parametrize("action", ["trust", "mute"])
def test_a_sender_without_an_address_cannot_be_trusted_or_muted(
    monkeypatch: pytest.MonkeyPatch, settings: Settings, action: str
) -> None:
    fixed_ids(monkeypatch, ITEM)
    with posted_store(replace(RECORD, sender="")) as store:
        discord = FakeDiscord()
        outcome, reply = answer(store, settings, discord, discord.press(f"mr:{action}:{ITEM}"))
        assert store.answer(ITEM) is None
    assert (outcome, reply) == ("no-sender", ephemeral("This email has no sender address."))


# Answers


def test_yes_records_the_title_and_updates_the_card(store: Store, settings: Settings) -> None:
    discord = FakeDiscord()
    outcome, reply = answer(store, settings, discord, discord.press(f"mr:yes:{ITEM}"))
    assert outcome == "answered"
    assert reply == {
        "type": 7,
        "data": checkpoint2_message(RECORD, VERDICT, ITEM, "Pay the November bill"),
    }
    assert store.answer(ITEM) == Answer(
        item_id=ITEM,
        answer="yes",
        title="Pay the November bill",
        answered_at=datetime(2026, 11, 10, 9, 0, tzinfo=UTC),
    )


@pytest.mark.parametrize(
    ("action", "status"), [("notask", None), ("mute", "muted")], ids=["not-a-task", "mute"]
)
def test_not_a_task_and_mute_close_the_item(
    store: Store, settings: Settings, action: str, status: str | None
) -> None:
    discord = FakeDiscord()
    outcome, reply = answer(store, settings, discord, discord.press(f"mr:{action}:{ITEM}"))
    assert (outcome, reply) == (
        "answered",
        {"type": 7, "data": answered_message(RECORD, VERDICT, ITEM, action, "")},
    )
    stored = store.answer(ITEM)
    assert stored is not None
    assert (stored.answer, stored.title) == (action, "")
    assert store.sender_status("billing@example.test") == status


def test_a_second_answer_is_refused_privately(store: Store, settings: Settings) -> None:
    discord = FakeDiscord()
    answer(store, settings, discord, discord.press(f"mr:notask:{ITEM}"))
    outcome, reply = answer(store, settings, discord, discord.press(f"mr:mute:{ITEM}"))
    assert (outcome, reply) == ("already", ephemeral("This email is already answered."))
    assert store.sender_status("billing@example.test") is None
    stored = store.answer(ITEM)
    assert stored is not None
    assert stored.answer == "notask"


def test_edit_title_opens_the_form_with_the_title_filled_in(
    store: Store, settings: Settings
) -> None:
    discord = FakeDiscord()
    outcome, reply = answer(store, settings, discord, discord.press(f"mr:edit:{ITEM}"))
    assert (outcome, reply) == ("form", form("Pay the November bill"))
    assert store.answer(ITEM) is None


def test_yes_without_a_title_opens_the_form_with_the_subject(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    fixed_ids(monkeypatch, ITEM)
    unread = Verdict(
        outcome="rejected", trusted=False, verified=True, bulk=False, notify=True, reason="timeout"
    )
    with posted_store(verdict=unread) as store:
        discord = FakeDiscord()
        outcome, reply = answer(store, settings, discord, discord.press(f"mr:yes:{ITEM}"))
        assert store.answer(ITEM) is None
    assert (outcome, reply) == ("form", form("Your November bill"))


def test_a_submitted_title_is_recorded_and_updates_the_card(
    store: Store, settings: Settings
) -> None:
    discord = FakeDiscord()
    event = discord.submit(f"mr:title:{ITEM}", "  Pay the bill online  ")
    outcome, reply = answer(store, settings, discord, event)
    assert outcome == "answered"
    assert reply == {
        "type": 7,
        "data": checkpoint2_message(RECORD, VERDICT, ITEM, "Pay the bill online"),
    }
    stored = store.answer(ITEM)
    assert stored is not None
    assert (stored.answer, stored.title) == ("edit", "Pay the bill online")


@pytest.mark.parametrize(
    "value",
    ["   ", "P" * 101, "Pay\nnow", "Pay​now"],
    ids=["blank", "too-long", "line-break", "zero-width"],
)
def test_a_bad_title_is_refused_privately(store: Store, settings: Settings, value: str) -> None:
    discord = FakeDiscord()
    outcome, reply = answer(store, settings, discord, discord.submit(f"mr:title:{ITEM}", value))
    assert (outcome, reply) == (
        "bad-title",
        ephemeral("A title needs 1 to 100 characters on one line."),
    )
    assert store.answer(ITEM) is None


def test_a_failed_reply_keeps_the_answer_and_names_only_the_status(
    store: Store, settings: Settings
) -> None:
    discord = FakeDiscord()
    discord.failures.append(httpx.Response(500, text="oops"))
    with pytest.raises(DiscordUnavailable) as caught:
        answer(store, settings, discord, discord.press(f"mr:notask:{ITEM}"))
    assert str(caught.value) == "discord unavailable (500)"
    assert caught.value.__suppress_context__
    stored = store.answer(ITEM)
    assert stored is not None
    assert stored.answer == "notask"
