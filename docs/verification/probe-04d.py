"""Probe for phase 4d. Run from the repository root: .venv/bin/python docs/verification/probe-04d.py

1. Same results, same answer: random SPF, DKIM and DMARC outcomes (pass, fail or none, for the
   sender's domain or another) are written once as Gmail writes them and once as Microsoft
   does, on otherwise identical emails. `verified` must give Gmail's and Outlook's the same
   answer, which is stage 4's test at the layer where the providers differ.
2. No forgery: an Outlook email whose first header carries a server name or no `compauth` is
   never verified, nor is one whose passing Microsoft-shaped header comes second.
Pure checks; no network. Each check prints `ok` or `FAIL`; the last line is `FAILURES N`.
"""

import random
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path.cwd()
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from mailroom.record import Record  # noqa: E402

FAILURES = 0
rng = random.Random(44)
GMAIL = Record(
    provider="gmail",
    message_id="personal/m1",
    thread_id="personal/t1",
    received_at=datetime(2026, 11, 12, 9, 0, tzinfo=UTC),
    link="https://mail.google.com/mail/?authuser=owner@example.test#all/m1",
    sender="sam@example.test",
    sender_name="Sam",
    subject="Report",
    sent_at=None,
    body_text="",
    list_unsubscribe=False,
    authentication_results=(),
)
OUTLOOK = replace(
    GMAIL,
    provider="outlook",
    message_id="live/AAMk1=",
    thread_id="live/conversation-1",
    link="https://outlook.live.com/owa/?ItemID=AAMk1=",
)


def check(name: str, fn) -> None:
    global FAILURES
    try:
        result = fn()
    except Exception as error:
        result = f"raised {type(error).__name__}"
    ok = result is True
    print(f"{name}: {'ok' if ok else 'FAIL ' + str(result)}")
    if not ok:
        FAILURES += 1


def gmail_header(spf: tuple[str, str], dkim: tuple[str, str], dmarc: tuple[str, str]) -> str:
    return (
        f"mx.google.com; dkim={dkim[0]} header.i=@{dkim[1]} header.s=s1; "
        f"spf={spf[0]} (google.com: domain of b@{spf[1]}) smtp.mailfrom=b@{spf[1]}; "
        f"dmarc={dmarc[0]} (p=REJECT) header.from={dmarc[1]}"
    )


def microsoft_header(spf: tuple[str, str], dkim: tuple[str, str], dmarc: tuple[str, str]) -> str:
    return (
        f"spf={spf[0]} (sender IP is 192.0.2.1) smtp.mailfrom={spf[1]}; "
        f"dkim={dkim[0]} (signature was verified) header.d={dkim[1]};"
        f"dmarc={dmarc[0]} action=none header.from={dmarc[1]};compauth=pass reason=100"
    )


ALL_PASS = (("pass", "example.test"),) * 3
assert "header.from=example.test;compauth=pass" in microsoft_header(*ALL_PASS)
assert gmail_header(*ALL_PASS).startswith("mx.google.com; dkim=pass")
print("oracle self-check: ok")


def outcome() -> tuple[str, str]:
    return rng.choice(["pass", "pass", "fail", "none"]), rng.choice(
        ["example.test", "example.test", "mail.example.test", "other.example.test"]
    )


def same_results_same_answer() -> object:
    from mailroom.sender_auth import verified

    reached = {True: 0, False: 0}
    for trial in range(4000):
        spf, dkim, dmarc = outcome(), outcome(), outcome()
        gmail = verified(replace(GMAIL, authentication_results=(gmail_header(spf, dkim, dmarc),)))
        outlook = verified(
            replace(OUTLOOK, authentication_results=(microsoft_header(spf, dkim, dmarc),))
        )
        if gmail != outlook:
            return f"trial {trial}: gmail {gmail}, outlook {outlook} for {spf}, {dkim}, {dmarc}"
        reached[gmail] += 1
    if min(reached.values()) < 200:
        return f"too few cases: {reached}"
    return True


def no_forgery() -> object:
    from mailroom.sender_auth import verified

    forged = microsoft_header(*ALL_PASS)
    reached = {"second": 0, "server-name": 0, "no-compauth": 0}
    for trial in range(3000):
        kind = rng.choice(sorted(reached))
        if kind == "second":
            first = microsoft_header(
                ("fail", "example.test"), ("none", "none"), ("fail", "example.test")
            )
            first = first.replace("compauth=pass reason=100", "compauth=fail reason=000")
            headers = (first, forged)
        elif kind == "server-name":
            headers = (
                rng.choice(["mx.microsoft.com", "example.test", "mx.google.com"]) + "; " + forged,
            )
        else:
            headers = (forged.replace(";compauth=pass reason=100", ""),)
        if verified(replace(OUTLOOK, authentication_results=headers)):
            return f"trial {trial}: verified a {kind} header: {headers[0]!r}"
        reached[kind] += 1
    if not verified(replace(OUTLOOK, authentication_results=(forged,))):
        return "Microsoft's own passing header was not verified"
    if min(reached.values()) < 100:
        return f"too few cases: {reached}"
    return True


check("Gmail and Outlook verify the same results alike", same_results_same_answer)
check("no forged or misplaced header verifies an Outlook email", no_forgery)
print(f"FAILURES {FAILURES}")
