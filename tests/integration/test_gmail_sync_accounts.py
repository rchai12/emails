from collections.abc import Iterator

import httpx
import pytest

from mailroom import clock
from mailroom.config import get_settings
from mailroom.gmail import GmailClient
from mailroom.gmail_sync import sync_gmail
from mailroom.store import Store, open_store
from tests.fakes import FakeGmail, FakeKeychain
from tests.integration.test_gmail_sync import NOW, deliver, fetched

ACCOUNTS = ("personal", "work")


@pytest.fixture
def mailboxes(fake_keychain: FakeKeychain, monkeypatch: pytest.MonkeyPatch) -> dict[str, FakeGmail]:
    monkeypatch.setattr(clock, "now", lambda: NOW)
    found = {}
    for account in ACCOUNTS:
        for name in ("client-id", "client-secret", "refresh-token"):
            fake_keychain.secrets[("mailroom", f"gmail.{account}.{name}")] = f"{name}-1"
        fake = FakeGmail()
        fake.email_address = f"{account}@example.test"
        found[account] = fake
    return found


@pytest.fixture
def store() -> Iterator[Store]:
    with open_store(get_settings()) as opened:
        yield opened


def client(fake: FakeGmail, account: str) -> GmailClient:
    return GmailClient(account, httpx.Client(transport=httpx.MockTransport(fake.handler)))


def test_two_accounts_keep_messages_that_share_a_gmail_id(
    mailboxes: dict[str, FakeGmail], store: Store
) -> None:
    for account in ACCOUNTS:
        deliver(mailboxes[account], 1)
    assert sync_gmail(client(mailboxes["personal"], "personal"), store).stored == ("personal/m1",)
    assert sync_gmail(client(mailboxes["work"], "work"), store).stored == ("work/m1",)
    assert fetched(mailboxes["work"]) == ["m1"]
    personal = store.get("gmail", "personal/m1").record
    work = store.get("gmail", "work/m1").record
    assert (personal.thread_id, work.thread_id) == ("personal/t1", "work/t1")
    assert (personal.link, work.link) == (
        "https://mail.google.com/mail/?authuser=personal@example.test#all/m1",
        "https://mail.google.com/mail/?authuser=work@example.test#all/m1",
    )
    assert store.get("gmail", "m1") is None


def test_a_message_stored_for_one_account_is_skipped_only_there(
    mailboxes: dict[str, FakeGmail], store: Store
) -> None:
    for account in ACCOUNTS:
        deliver(mailboxes[account], 1)
    sync_gmail(client(mailboxes["personal"], "personal"), store)
    sync_gmail(client(mailboxes["work"], "work"), store)
    for account in ACCOUNTS:
        mailboxes[account].add_labels("m1", "INBOX")
    assert sync_gmail(client(mailboxes["personal"], "personal"), store).stored == ()
    assert sync_gmail(client(mailboxes["work"], "work"), store).stored == ()
    assert fetched(mailboxes["personal"]) == ["m1"]
    assert fetched(mailboxes["work"]) == ["m1"]
