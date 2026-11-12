"""Probe for phase 1e. Run from the repository root: .venv/bin/python docs/verification/probe-01e.py

It builds Authentication-Results headers from random results, written the way mail servers write
them (any case, extra spaces, version numbers, comments that may hold a fake `pass` or a `;`), and
compares `verified` and `screen` with an oracle that reads the results, not the text. The
database is in a temporary folder. Each check prints `ok` or `FAIL`; the last line is
`FAILURES N`.
"""

import os
import random
import sys
import tempfile
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path.cwd()
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
TMP = Path(tempfile.mkdtemp(prefix="probe01e-"))
os.environ["HOME"] = str(TMP / "home")
os.environ["MAILROOM_DATA_DIR"] = str(TMP / "data")

from mailroom.record import Record  # noqa: E402

SENDER_DOMAIN = "example.test"
DOMAINS = [
    "example.test",
    "Example.TEST",
    "mail.example.test",
    "badexample.test",
    "example.test.evil.test",
    "other.test",
]
RESULTS = ["pass", "pass", "fail", "softfail", "none", "neutral", "temperror"]
FAILURES = 0
rng = random.Random(14)


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


# The oracle reads structured results: (method, result, domain) and the server that wrote them.
def aligned(domain: str) -> bool:
    domain = domain.lower()
    return domain == SENDER_DOMAIN or domain.endswith("." + SENDER_DOMAIN)


def oracle(server: str, results: list[tuple[str, str, str]]) -> bool:
    if server.lower() != "mx.google.com":
        return False
    passed = {(method, domain.lower()) for method, result, domain in results if result == "pass"}
    if ("dmarc", SENDER_DOMAIN) in passed:
        return True
    spf = any(method == "spf" and aligned(domain) for method, domain in passed)
    dkim = any(method == "dkim" and aligned(domain) for method, domain in passed)
    return spf and dkim


assert oracle("mx.google.com", [("dmarc", "pass", "Example.TEST")])
assert not oracle("mx.google.com", [("dmarc", "pass", "mail.example.test")])
assert oracle(
    "MX.google.com", [("spf", "pass", "mail.example.test"), ("dkim", "pass", "example.test")]
)
assert not oracle(
    "mx.google.com", [("spf", "pass", "badexample.test"), ("dkim", "pass", "example.test")]
)
assert not oracle("mx.evil.test", [("dmarc", "pass", "example.test")])
print("oracle self-check: ok")

try:
    from mailroom.config import get_settings
    from mailroom.rules import Screening, screen
    from mailroom.sender_auth import parse_results, verified
    from mailroom.store import open_store
except Exception as error:
    print(f"import: FAIL raised {type(error).__name__}")
    print("FAILURES 1")
    sys.exit(1)

BASE = Record(
    provider="gmail",
    message_id="m1",
    thread_id="t1",
    received_at=datetime(2026, 11, 12, 9, 0, tzinfo=UTC),
    link="https://mail.google.com/mail/?authuser=owner@example.test#all/m1",
    sender="billing@example.test",
    sender_name="Billing",
    subject="Your bill",
    sent_at=None,
    body_text="",
    list_unsubscribe=False,
    authentication_results=(),
)


def cased(text: str) -> str:
    return "".join(c.upper() if rng.random() < 0.3 else c for c in text)


def comment() -> str:
    inner = rng.choice(
        [
            "google.com: domain of x designates 192.0.2.1 as permitted sender",
            "dmarc=pass header.from=example.test",
            "spf=pass smtp.mailfrom=example.test; dkim=pass header.d=example.test",
            "p=REJECT (nested dmarc=pass header.from=example.test) dis=NONE",
        ]
    )
    return f"({inner})"


def gap() -> str:
    return rng.choice([" ", "  ", " ", f" {comment()} "])


def render(method: str, result: str, domain: str) -> str:
    if method == "dmarc":
        prop = f"{cased('header.from')}={domain}"
    elif method == "spf":
        prop = f"{cased('smtp.mailfrom')}=" + rng.choice([domain, f"bounce@{domain}"])
    else:
        prop = rng.choice([f"{cased('header.d')}={domain}", f"{cased('header.i')}=@{domain}"])
        prop += rng.choice(["", " header.s=s1", " header.b=abc"])
    return f"{cased(method)}={cased(result)}{gap()}{prop}"


def random_header() -> tuple[str, list[tuple[str, str, str]], str]:
    server = rng.choice(["mx.google.com"] * 4 + ["mx.evil.test", "google.com"])
    results = [
        (rng.choice(["dkim", "spf", "dmarc"]), rng.choice(RESULTS), rng.choice(DOMAINS))
        for _ in range(rng.randrange(0, 5))
    ]
    parts = [render(*result) for result in results]
    if rng.random() < 0.2:
        parts.insert(rng.randrange(len(parts) + 1), cased("arc=pass"))
    head = cased(server) + rng.choice(["", " 1"])
    return head + "".join(rng.choice([";", "; ", " ;  "]) + part for part in parts), results, server


def verification_follows_the_oracle() -> object:
    for _ in range(3000):
        header, results, server = random_header()
        want = oracle(server, results)
        extra = [random_header()[0] for _ in range(rng.randrange(0, 3))]
        got = verified(replace(BASE, authentication_results=(header, *extra)))
        if got is not want:
            return f"{header!r}: verified {got}, want {want}"
        forged = verified(
            replace(BASE, authentication_results=("mx.google.com; dmarc=fail", header))
        )
        if forged:
            return f"a pass after the provider's own header counted: {header!r}"
    return True


def junk_never_raises() -> object:
    alphabet = "abc=;()@. \t\\\"'xyz"
    for _ in range(3000):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randrange(0, 80)))
        server, results = parse_results(text)
        if not isinstance(server, str) or not isinstance(results, tuple):
            return f"{text!r}: returned {server!r}, {results!r}"
        if not isinstance(verified(replace(BASE, authentication_results=(text,))), bool):
            return f"{text!r}: verified is not a bool"
    return True


def screening_follows_the_rules() -> object:
    with open_store(get_settings()) as store:
        for _ in range(400):
            sender = rng.choice(["billing@example.test", "other@example.test", ""])
            status = rng.choice(["trusted", "muted", None])
            store.set_sender_status("billing@example.test", status)
            header, results, server = random_header()
            record = replace(
                BASE,
                sender=sender,
                list_unsubscribe=rng.random() < 0.5,
                authentication_results=(header,),
            )
            is_verified = sender == "billing@example.test" and oracle(server, results)
            known = status if sender == "billing@example.test" else None
            want = Screening(
                action="drop" if known == "muted" else "extract",
                trusted=known == "trusted" and is_verified,
                verified=is_verified,
                bulk=record.list_unsubscribe,
            )
            if sender == "other@example.test":
                want = replace(want, verified=oracle(server, results))
            got = screen(record, store)
            if got != want:
                return f"{sender!r} {status} {header!r}: got {got}, want {want}"
    return True


check("verified follows the provider's own results only", verification_follows_the_oracle)
check("any header text parses without raising", junk_never_raises)
check(
    "screening drops only muted senders and trusts only verified ones", screening_follows_the_rules
)
print(f"FAILURES {FAILURES}")
