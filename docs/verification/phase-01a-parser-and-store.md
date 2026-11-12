# Verification guide: Phase 1a (parser and store)

Spec: `docs/phases/phase-01a-parser-and-store.md`. Follow `docs/phase-conventions.md` ("For the verifier"). Never connect to a real mail provider, Discord, the tasks app or the model, never read the Keychain, and never open the real data folder: every test and the probe use temporary folders.

## 1. Coder ran

Stop with FAIL ("the coder did not run") if any of these is missing:

- `src/mailroom/mime.py` and `src/mailroom/store.py`
- `grep -c "^## Phase 1a: " docs/progress.md` prints `1`

Stop with FAIL ("the baseline is not committed") if `git ls-files --error-unmatch docs/phases/phase-01a-parser-and-store.md src/mailroom/record.py src/mailroom/schema.py tests/unit/test_mime.py tests/integration/test_store.py` fails: G5 and G6 can only be judged against a committed spec and given files.

## 2. Gates

Run each from the repository root, in this order.

| # | Command | Must show |
|---|---|---|
| G1 | `.venv/bin/python scripts/check.py --first core` | last line `All checks passed.`; `tests (core): passed`; `critical coverage: passed`; in the `tests` step at least 165 passed (96 + 69), 0 failed, 0 skipped, no warnings summary; every `Sections:` line 0 failed |
| G2 | `.venv/bin/python -m coverage report --include=src/mailroom/mime.py,src/mailroom/store.py,src/mailroom/record.py,src/mailroom/schema.py --fail-under=100` (right after G1) | exit 0, `TOTAL` at `100%` |
| G3 | `.venv/bin/python -m pytest tests/unit/test_record.py tests/unit/test_mime.py tests/integration/test_store.py --no-cov -q` | `69 passed` |
| G4 | `.venv/bin/python scripts/check_reports.py --phase 1a` | `Reports OK.` |
| G5 | `git diff HEAD --stat -- src/mailroom/record.py src/mailroom/schema.py scripts/critical_modules.txt tests/unit/test_record.py tests/unit/test_mime.py tests/integration/test_store.py` | no output |
| G6 | `git status --short` | only: `src/mailroom/mime.py`, `src/mailroom/store.py`, `docs/progress.md`, and, if present, `tests/unit/test_mime_more.py`, `tests/integration/test_store_more.py` |
| G7 | `.venv/bin/python -m pip list --format=freeze` | the same packages as before this phase: no new dependency |

## 3. Spot checks

For each row:
1. Copy the module outside the repository.
2. Make the change described in the module the coder wrote: the line or lines that do what the "Change" cell names.
3. Run the deciding test with `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest '<test>' --no-cov -vv`, and confirm it fails with the "Broken" value.
4. Restore the module from your copy, delete `src/mailroom/__pycache__`, and confirm `git diff` is as before.

A different failure from the "Broken" column is a note, not a finding; a pass is a finding. S2 assumes umask `022`; under another umask, the broken mode is what that umask gives, and anything but `0o600` confirms the row.

| # | Module | Change | Deciding test | Correct | Broken |
|---|---|---|---|---|---|
| S1 | `store.py` | remove the `PRAGMA secure_delete` statement | `tests/integration/test_store.py::test_cleared_text_is_gone_from_the_file` | marker absent | `b"ZQX-BODY-7"` found in the file |
| S2 | `store.py` | remove the step that sets the database file's mode | `tests/integration/test_store.py::test_opening_creates_a_private_database` | `0o600` (384) | `0o644` (420) |
| S3 | `store.py` | compare with `<` instead of `<=` when choosing expired rows | `tests/integration/test_store.py::test_email_text_is_cleared_24_hours_after_fetch` | second clear returns `1` | `0` |
| S4 | `store.py` | drop the `text_cleared_at IS NULL` condition from the clearing query | `tests/integration/test_store.py::test_email_text_is_cleared_24_hours_after_fetch` | third clear returns `1` | `2` |
| S5 | `store.py` | on a duplicate key, replace the row (`INSERT OR REPLACE`, or `ON CONFLICT ... DO UPDATE`) | `tests/integration/test_store.py::test_the_same_message_is_stored_once` | second `add` returns `False` | `True` |
| S6 | `store.py` | remove the check that refuses a newer `user_version` | `tests/integration/test_store.py::test_a_newer_schema_is_refused` | `StoreError` | no exception |
| S7 | `store.py` | store times with `isoformat(timespec="microseconds")` without converting to UTC | `tests/integration/test_store.py::test_times_are_stored_as_utc_text` | `'2026-11-03T14:15:00.000250+00:00'` | `'2026-11-03T19:45:00.000250+05:30'` |
| S8 | `store.py` | in `get`, pass a cleared row's `NULL` body through as `None` instead of `""` | `tests/integration/test_store.py::test_email_text_is_cleared_24_hours_after_fetch` | `body_text=''` | `body_text=None` |
| S9 | `mime.py` | keep the address's case (drop the lower-casing) | `tests/unit/test_mime.py::test_a_plain_message_becomes_a_record` | `'billing@billing.example.test'` | `'Billing@Billing.Example.TEST'` |
| S10 | `mime.py` | ask `get_body` for `("html", "plain")` | `tests/unit/test_mime.py::test_the_body_is_the_plain_part_or_the_html_part_as_text[alternative]` | `'Plain part'` | `'HTML part'` |
| S11 | `mime.py` | in `clean_line`, keep `Cf` characters (remove only `Cc`) | `tests/unit/test_mime.py::test_clean_line_collapses_whitespace_and_drops_invisible_characters` | `'Pay the bill now!'` | `'Pay the bill now​!‮'` |
| S12 | `mime.py` | in `html_to_text`, keep the text of `script` and `style` | `tests/unit/test_mime.py::test_html_skips_script_and_style_even_unclosed` | `'Hi\n\nthere'` | contains `'p {}'` |
| S13 | `mime.py` | add requested newlines together instead of taking the largest | `tests/unit/test_mime.py::test_html_blocks_links_and_scripts` | contains `'One\nTwo'` | `'One\n\nTwo'` |
| S14 | `mime.py` | let an exception from `parsebytes` propagate (remove that fallback) | `tests/unit/test_mime.py::test_a_message_the_email_package_cannot_parse_keeps_its_text` | a `Record` | `IndexError` |
| S15 | `mime.py` | read `From` without the guard | `tests/unit/test_mime.py::test_a_header_the_email_package_cannot_read_counts_as_missing` | `('', '')` | `AttributeError` |
| S16 | `mime.py` | keep every `Authentication-Results` value (drop the limit of 10) | `tests/unit/test_mime.py::test_authentication_results_are_kept_in_order_with_limits[twelve]` | 10 values | 12 values |
| S17 | `mime.py` | let an exception from `get_content` propagate (remove the payload fallback) | `tests/unit/test_mime.py::test_the_body_is_the_plain_part_or_the_html_part_as_text[unknown-charset]` | `'café �'` | `LookupError` |

## 4. Probe

Save the script below outside the repository (for example `/tmp/probe-01a.py`), run it from the repository root with `.venv/bin/python /tmp/probe-01a.py`, and delete it afterwards. Every line must end in `ok`; the last line must be `FAILURES 0`.

- **A stop at the probe's own lines is the probe's fault.** That means the `assert` lines before `oracle self-check: ok`, or a probe check reporting "adjust the seed". Report it under "For the architect", not as a finding.
- **It stays off real systems.** The probe sets `HOME` and `MAILROOM_DATA_DIR` to a new temporary folder before importing `mailroom`, replaces `clock.now` for the store checks, and touches no network or Keychain.
- **Its oracle comes from the spec.** It implements requirements 3 to 6 itself, from the spec's text, and compares `clean_line`, `clean_text` and `html_to_text` with it on random input.
- **What it checks beyond that.** It fuzzes `parse_message` with corrupted headers (requirement 7: it never raises, and every field stays clean and within its limit). It runs `Store` against an in-memory model of adds and clears, then checks:
  - the file holds no cleared text
  - the data folder holds only the database
  - the file's mode is `0o600` even under umask `0`

```python
"""Probe for phase 1a. Run from the repository root:

    .venv/bin/python /path/to/probe-01a.py

It imports `mailroom` from ./src, uses a temporary folder for HOME and the data folder, and
touches no network, mailbox or Keychain. The oracle below is written from the spec's rules only.
"""

import os
import random
import re
import sqlite3
import stat
import sys
import tempfile
import unicodedata
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "src"))
TMP = Path(tempfile.mkdtemp(prefix="probe01a-"))
os.environ["HOME"] = str(TMP / "home")
os.environ["MAILROOM_DATA_DIR"] = str(TMP / "data")
for key in list(os.environ):
    if key.startswith("MAILROOM_") and key != "MAILROOM_DATA_DIR":
        del os.environ[key]

FAILURES = 0


def check(name, fn):
    global FAILURES
    try:
        result = fn()
    except Exception as error:  # noqa: BLE001
        result = f"raised {type(error).__name__}"
    ok = result is True
    print(f"{name}: {'ok' if ok else 'FAIL ' + str(result)}")
    if not ok:
        FAILURES += 1


# ---------------------------------------------------------------------------------------------
# Oracle, from the spec's rules.

BODY_LIMIT = 100_000
ADDRESS = re.compile(r"[^@\s<>]+@[^@\s<>]+")


def ref_fix(text):
    out, run = [], bytearray()
    for ch in text:
        code = ord(ch)
        if 0xDC80 <= code <= 0xDCFF:
            run.append(code - 0xDC00)
            continue
        if run:
            out.append(bytes(run).decode("utf-8", "replace"))
            run.clear()
        out.append("�" if 0xD800 <= code <= 0xDFFF else ch)
    if run:
        out.append(bytes(run).decode("utf-8", "replace"))
    return "".join(out)


def invisible(ch):
    return unicodedata.category(ch) in ("Cc", "Cf")


def ref_clean_line(text, limit):
    text = ref_fix(text)
    text = "".join(ch for ch in text if not (invisible(ch) and not ch.isspace()))
    return " ".join(text.split())[:limit].rstrip()


def ref_clean_text(text, limit):
    text = ref_fix(text).replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(ch for ch in text if ch in "\n\t" or not invisible(ch))
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text).strip("\n")
    return text[:limit].rstrip()


LINE_TAGS = {"br", "div", "li", "tr", "dt", "dd", "header", "footer", "section", "article",
             "aside", "address", "pre", "hr"}
PARAGRAPH_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "dl", "table", "blockquote"}


def collapse_spaces(text):
    out, in_space = [], False
    for ch in text:
        if ch.isspace():
            if not in_space:
                out.append(" ")
            in_space = True
        else:
            out.append(ch)
            in_space = False
    return "".join(out)


class RefHtml(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.pending, self.started = [], 0, False
        self.skip = None
        self.href, self.anchor = None, []

    def request(self, count):
        self.pending = max(self.pending, count)

    def text(self, piece):
        if piece == " " and self.pending:
            return
        if self.started and self.pending:
            self.out.append("\n" * self.pending)
        self.pending = 0
        self.started = True
        self.out.append(piece)
        if self.href is not None:
            self.anchor.append(piece)

    def breaks(self, tag):
        if tag in PARAGRAPH_TAGS:
            self.request(2)
        elif tag in LINE_TAGS:
            self.request(1)

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip = tag
            return
        self.breaks(tag)
        if tag == "a":
            hrefs = [value for name, value in attrs if name == "href"]
            href = hrefs[0].strip() if hrefs and hrefs[0] is not None else None
            ok = href is not None and href.lower().startswith(("http://", "https://", "mailto:"))
            self.href, self.anchor = (href if ok else None), []

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            if self.skip == tag:
                self.skip = None
            return
        self.breaks(tag)
        if tag in ("td", "th"):
            self.text(" ")
        if tag == "a" and self.href is not None:
            href, self.href = self.href, None
            if " ".join("".join(self.anchor).split()) != href:
                self.text(f" ({href})")

    def handle_data(self, data):
        if self.skip is None:
            self.text(collapse_spaces(data))


def ref_html(html):
    parser = RefHtml()
    parser.feed(html)
    parser.close()
    text = "".join(parser.out)
    text = "\n".join(" ".join(line.split()) for line in text.split("\n"))
    return ref_clean_text(text, BODY_LIMIT)


# Self-check on known cases (the given tests' values). A stop here is the probe's fault.
assert ref_clean_line("  Pay\tthe\r\n  bill\x00 now​!‮ ", 100) == "Pay the bill now!"
assert ref_clean_line("abcde fghij", 6) == "abcde"
assert ref_clean_line("Jos\udcc3\udca9", 100) == "José"
assert ref_clean_line("\ud800x", 100) == "�x"
assert ref_clean_text("abc\ndef", 4) == "abc"
text = "\r\n  \r\nHello  \r\nWorld\x07\tnow\t\r\rBye​\n\n\n\n  indented\n\n"
assert ref_clean_text(text, 1000) == "Hello\nWorld\tnow\n\nBye\n\n  indented"
assert ref_html(
    "<html><head><style>p { color: red }</style></head><body>"
    "<p>Your bill&nbsp;is <b>due</b>.</p>"
    '<div>Pay at <a href="https://pay.example.test/bill?id=7&amp;x=1">the portal</a></div>'
    "<script>track()</script><ul><li>One</li><li>Two</li></ul>Line<br>break<br/>done</body></html>"
) == (
    "Your bill is due.\n\nPay at the portal (https://pay.example.test/bill?id=7&x=1)\n\n"
    "One\nTwo\n\nLine\nbreak\ndone"
)
assert ref_html("<P>Hi</P><STYLE>p {}</STYLE><SCRIPT>t()</SCRIPT><p>there</p><script>x") == (
    "Hi\n\nthere"
)
assert ref_html(
    "<table><tr><td>Amount</td><td>$42.00</td></tr>\n  <tr><td>Due</td><td>Nov 20</td></tr>"
    '</table><p><a href="https://x.example.test/a">https://x.example.test/a</a>'
    ' and <a href="javascript:evil()">click</a> and <a href="mailto:help@x.example.test">'
    'email us</a> and <a href=" HTTPS://X.example.test/B ">B</a></p>'
) == (
    "Amount $42.00\nDue Nov 20\n\nhttps://x.example.test/a and click and email us"
    " (mailto:help@x.example.test) and B (HTTPS://X.example.test/B)"
)
print("oracle self-check: ok")

# ---------------------------------------------------------------------------------------------
# The code under test.

from mailroom import clock  # noqa: E402  (phase 0)
from mailroom.config import get_settings  # noqa: E402  (phase 0)
from mailroom.record import Envelope, Record  # noqa: E402  (given)


class Missing:
    def __init__(self, name):
        self.name = name

    def __getattr__(self, attribute):
        raise ImportError(self.name)


try:
    from mailroom import mime
except Exception:  # noqa: BLE001
    mime = Missing("mime")
try:
    from mailroom import store
except Exception:  # noqa: BLE001
    store = Missing("store")

rng = random.Random(1)
TRICKY = [" ", "\t", "\r", "\n", "\r\n", "\x00", "\x07", "\x0b", "\x0c", "\x1c", "\x7f", "\x85",
          "\xa0", "​", "‍", "‮", " ", "　", "﻿", "�", "\udcc3",
          "\udca9", "\udcff", "\udc80", "\ud800", "\udfff", "a", "b", "Z", "é", "日", "😀", "-", ".",
          "<", ">", "&", "  ", "\n\n\n"]


def random_text(size):
    return "".join(rng.choice(TRICKY) for _ in range(rng.randrange(size)))


def compare_many(fn, ref, count, size, limits):
    for _ in range(count):
        text, limit = random_text(size), rng.choice(limits)
        got, want = fn(text, limit), ref(text, limit)
        if got != want:
            return f"{text!r} limit {limit}: got {got!r}, want {want!r}"
    return True


check("clean_line matches the rules on random text",
      lambda: compare_many(mime.clean_line, ref_clean_line, 600, 40, [0, 1, 3, 8, 20, 100]))
check("clean_text matches the rules on random text",
      lambda: compare_many(mime.clean_text, ref_clean_text, 600, 60, [0, 1, 5, 12, 40, 1000]))

WORDS = ["Pay", "bill", "now", "due", "&amp;", "&nbsp;", "&#x41;", "&bogus;", " ", "\n ", "\t"]
TAGS = ["p", "div", "br", "li", "ul", "td", "th", "tr", "table", "h2", "b", "span", "hr",
        "blockquote", "pre", "em"]
HREFS = ["https://pay.example.test/x", "HTTP://a.example.test", " mailto:h@example.test ",
         "javascript:evil()", "ftp://f.example.test", "Pay", None]


def random_html():
    parts = []
    for _ in range(rng.randrange(1, 40)):
        kind = rng.random()
        if kind < 0.35:
            parts.append(rng.choice(WORDS))
        elif kind < 0.6:
            parts.append(f"<{rng.choice(TAGS)}>")
        elif kind < 0.8:
            parts.append(f"</{rng.choice(TAGS)}>")
        elif kind < 0.88:
            href = rng.choice(HREFS)
            attr = "" if href is None else f' href="{href}"'
            parts.append(f"<a{attr}>{rng.choice(WORDS + ['https://pay.example.test/x'])}</a>")
        elif kind < 0.93:
            parts.append(f"<{rng.choice(['script', 'style'])}>SECRET{rng.randrange(9)}")
            if rng.random() < 0.8:
                parts.append(f"</{rng.choice(['script', 'style'])}>")
        else:
            parts.append(f"<{rng.choice(TAGS)}/>")
    return "".join(parts)


def html_many():
    for _ in range(800):
        html = random_html()
        got, want = mime.html_to_text(html), ref_html(html)
        if got != want:
            return f"{html!r}: got {got!r}, want {want!r}"
        if "SECRET" in got:
            return f"{html!r}: script or style text kept"
    return True


check("html_to_text matches the rules on random HTML", html_many)

ENVELOPE = Envelope(
    provider="gmail",
    message_id="18c2f0a1b2c3d4e5",
    thread_id="18c2f0a1b2c3d4e0",
    received_at=datetime(2026, 11, 3, 14, 15, 5, tzinfo=UTC),
    link="https://mail.google.com/mail/u/0/#all/18c2f0a1b2c3d4e5",
)
HEAD = [b"Authentication-Results: mx.google.com; dmarc=pass header.from=example.test",
        b"From: Billing Team <billing@example.test>", b"Subject: Your bill",
        b"Date: Tue, 03 Nov 2026 09:15:00 -0500", b"List-Unsubscribe: <mailto:u@example.test>",
        b"MIME-Version: 1.0", b"Content-Type: text/plain; charset=utf-8",
        b"Content-Transfer-Encoding: quoted-printable"]
BODY = b"Hello =E9 there\r\n"
JUNK = [bytes([i]) for i in range(256)] + [
    b"=?", b"?=", b"=?utf-8?b?", b"=?utf-8?q?", b"<", b">", b'"', b"(", b")", b",", b";", b":",
    b"@", b"\\", b"\r\n", b"\r\n ", b"boundary=", b"charset=", b"multipart/mixed", b"text/html"]


def corrupt():
    head = list(HEAD)
    k = rng.randrange(len(head))
    name, _, value = head[k].partition(b": ")
    junk = b"".join(rng.choice(JUNK) for _ in range(rng.randrange(1, 30)))
    keep = value[: rng.randrange(len(value) + 1)] if rng.random() < 0.7 else b""
    head[k] = name + b": " + keep + junk
    return b"\r\n".join(head) + b"\r\n\r\n" + BODY


def record_problem(record):
    if not isinstance(record, Record):
        return "not a Record"
    if (record.provider, record.message_id, record.thread_id, record.received_at,
            record.link) != ("gmail", ENVELOPE.message_id, ENVELOPE.thread_id,
                             ENVELOPE.received_at, ENVELOPE.link):
        return "envelope fields changed"
    sender = record.sender
    if sender and not (ADDRESS.fullmatch(sender) and sender == sender.lower() and len(sender) <= 254):
        return f"bad sender {sender!r}"
    if record.sender_name != ref_clean_line(record.sender_name, 100):
        return f"unclean sender_name {record.sender_name!r}"
    if record.subject != ref_clean_line(record.subject, 200):
        return f"unclean subject {record.subject!r}"
    if record.body_text != ref_clean_text(record.body_text, BODY_LIMIT):
        return "unclean body"
    results = record.authentication_results
    if len(results) > 10 or any(not r or r != ref_clean_line(r, 2000) for r in results):
        return "bad authentication_results"
    if record.sent_at is not None and record.sent_at.utcoffset() != timedelta(0):
        return "sent_at not UTC"
    return None


def fuzz_parse():
    crashers = [b"From: :;\xe6", b"Content-Type: charset=\x00", b"Content-Type: ;\xd9*"]
    raws = [b"\r\n".join([*HEAD, c]) + b"\r\n\r\n" + BODY for c in crashers]
    raws += [corrupt() for _ in range(3000)]
    raws += [b"", b"\r\n", b"\xff\xfe\x00", b"From: a@example.test"]
    for raw in raws:
        try:
            record = mime.parse_message(raw, ENVELOPE)
        except Exception as error:  # noqa: BLE001
            return f"{raw[:120]!r}: raised {type(error).__name__}"
        problem = record_problem(record)
        if problem:
            return f"{raw[:120]!r}: {problem}"
    return True


check("parse_message never raises and keeps every field clean", fuzz_parse)


def parse_cases():
    def parsed(*lines, body=b"Hi\r\n"):
        return mime.parse_message(b"\r\n".join(lines) + b"\r\n\r\n" + body, ENVELOPE)

    # The email package raises reading this header (a newline in an address part), so it
    # counts as missing.
    found = parsed(b"From: =?utf-8?q?A=0AB?= <X@Example.TEST>", b"Subject: s")
    if (found.sender, found.sender_name, found.subject) != ("", "", "s"):
        return f"encoded newline in name: {(found.sender, found.sender_name)!r}"
    found = parsed(b"From: Ann <X@Example.TEST>")
    if (found.sender, found.sender_name) != ("x@example.test", "Ann"):
        return f"lower-case address: {(found.sender, found.sender_name)!r}"
    found = parsed(b"Date: Tue, 03 Nov 2026 09:15:00 +0000 (UTC)")
    if found.sent_at != datetime(2026, 11, 3, 9, 15, tzinfo=UTC):
        return f"date with comment: {found.sent_at!r}"
    found = parsed(b"Subject: a\xe2\x80\x8bb", b"List-Unsubscribe: <https://u.example.test>")
    if (found.subject, found.list_unsubscribe) != ("ab", True):
        return f"subject or unsubscribe: {(found.subject, found.list_unsubscribe)!r}"
    found = parsed(b"Authentication-Results: a; x", b"Authentication-Results: b; y")
    if found.authentication_results != ("a; x", "b; y"):
        return f"order: {found.authentication_results!r}"
    found = parsed(b"From: a@example.test", body=b"no headers end")
    if found.sender != "a@example.test":
        return "plain message"
    return True


check("parse_message on a few more headers", parse_cases)

# ---------------------------------------------------------------------------------------------
# Store, against a model.

NOW = [datetime(2026, 11, 10, 0, 0, tzinfo=UTC)]
srng = random.Random(2)
clock.now = lambda: NOW[0]
BASE_RECORD = Record(
    provider="gmail", message_id="m0", thread_id="t0",
    received_at=datetime(2026, 11, 3, 14, 15, 5, tzinfo=UTC),
    link="https://mail.google.com/mail/u/0/#all/m0", sender="a@example.test",
    sender_name="Ann", subject="Subject KEEP", sent_at=None, body_text="",
    list_unsubscribe=False, authentication_results=(),
)


def marker(provider, key):
    return f"ZQXBODY{provider}{key}Q " * 20


def store_model():
    old_umask = os.umask(0)
    try:
        opened = store.open_store(get_settings())
    finally:
        os.umask(old_umask)
    model = {}
    with opened as db:
        for _ in range(400):
            NOW[0] += srng.choice([timedelta(0), timedelta(microseconds=1), timedelta(hours=1),
                                  timedelta(hours=5), timedelta(hours=23, minutes=59)])
            if srng.random() < 0.7:
                provider, key = srng.choice(["gmail", "outlook", "yahoo"]), f"m{srng.randrange(12)}"
                record = replace(BASE_RECORD, provider=provider, message_id=key,
                                 body_text=marker(provider, key),
                                 authentication_results=(f"mx.example.test; ZQXAUTH{key}",))
                fresh = (provider, key) not in model
                if db.add(record) is not fresh:
                    return f"add {provider} {key}: wrong answer"
                if fresh:
                    model[(provider, key)] = [record, NOW[0], None]
            else:
                due = [row for row in model.values()
                       if row[2] is None and row[1] <= NOW[0] - timedelta(hours=24)]
                for row in due:
                    row[2] = NOW[0]
                count = db.clear_expired_text()
                if count != len(due):
                    return f"clear: {count}, want {len(due)}"
        for late in range(3):
            record = replace(BASE_RECORD, message_id=f"late{late}",
                             body_text=marker("gmail", f"late{late}"))
            if db.add(record) is not True:
                return f"add late{late}: wrong answer"
            model[("gmail", f"late{late}")] = [record, NOW[0], None]
        due = [row for row in model.values()
               if row[2] is None and row[1] <= NOW[0] - timedelta(hours=24)]
        for row in due:
            row[2] = NOW[0]
        if db.clear_expired_text() != len(due):
            return "the last clear removed the wrong rows"
        for (provider, key), (record, fetched, cleared) in model.items():
            want = record if cleared is None else replace(record, body_text="",
                                                           authentication_results=())
            got = db.get(provider, key)
            if got is None or (got.record, got.fetched_at, got.text_cleared_at) != (
                want, fetched, cleared
            ):
                return f"get {provider} {key}: {got!r}"
    path = TMP / "data" / "mailroom.sqlite3"
    content = path.read_bytes()
    for (provider, key), (_, _, cleared) in model.items():
        if cleared is not None and marker(provider, key).encode()[:20] in content:
            return f"cleared text of {provider} {key} is still in the file"
    if not any(row[2] is None for row in model.values()):
        return "probe never kept uncleared text (adjust the seed)"
    if sorted(p.name for p in path.parent.iterdir()) != ["mailroom.sqlite3"]:
        return f"extra files: {sorted(p.name for p in path.parent.iterdir())}"
    if stat.S_IMODE(path.stat().st_mode) != 0o600:
        return f"mode {oct(stat.S_IMODE(path.stat().st_mode))}"
    return True


check("store matches a model of adds and clears, and the file holds no cleared text",
      store_model)


def schema_versions():
    path = TMP / "data" / "mailroom.sqlite3"
    connection = sqlite3.connect(path)
    version = connection.execute("PRAGMA user_version").fetchone()
    connection.execute("PRAGMA user_version = 2")
    connection.close()
    if version != (1,):
        return f"user_version {version}"
    try:
        store.open_store(get_settings())
    except store.StoreError as error:
        return True if str(error) == "unsupported schema version: 2" else f"text {error}"
    return "no StoreError"


check("schema version is 1 and a newer one is refused", schema_versions)

print(f"FAILURES {FAILURES}")
```

## 5. Searches

Each prints nothing, except Q5, which must print exactly one line (the `secure_delete` statement). A match is a finding against the rule it names.

| # | Rule | Command |
|---|---|---|
| Q1 | no network code | `git grep --untracked -n -E 'import (socket\|ssl\|imaplib\|smtplib\|http\|urllib\|requests\|httpx)([^A-Za-z_]\|$)\|from (socket\|ssl\|imaplib\|smtplib\|http\|urllib\|requests\|httpx)([^A-Za-z_]\|$)' -- src` |
| Q2 | email text is never logged or printed | `git grep --untracked -n -E 'print\(\|logging\|logger\|warnings\.warn' -- src ':!src/mailroom/cli.py'` |
| Q3 | time only through `clock.now()`, called through the module | `git grep --untracked -n -E 'datetime\.now\|datetime\.utcnow\|date\.today\|time\.time\(\|from mailroom\.clock import' -- src ':!src/mailroom/clock.py'` |
| Q4 | default journal, no WAL file holding old text | `git grep --untracked -n -E -i 'journal_mode\|wal_\|vacuum' -- src` |
| Q5 | cleared text is overwritten in the file (one line expected) | `git grep --untracked -n -E -i 'secure_delete' -- src/mailroom/store.py` |
| Q6 | SQL values are parameters | `git grep --untracked -n -E 'execute(script\|many)?\(f' -- src/mailroom/store.py \| grep -v user_version` |
| Q7 | no coverage or lint exclusions | `git grep --untracked -n -E 'pragma: no cover\|noqa' -- src/mailroom/mime.py src/mailroom/store.py` |

(In the table, `\|` is a `|` in the command.)

## 6. Reasonable variations

These are correct even though the spec does not spell them out:

- **Surrogates.** Repaired with `text.encode("utf-8", "surrogateescape")` after replacing other surrogates, or character by character; any form that gives the spec's result.
- **HTML.** `html_to_text` as an `HTMLParser` subclass, or a parser with callbacks; private helper names of any kind.
- **Headers.** One helper that reads a header and returns `None` on any `Exception`, used for every header read.
- **`except Exception`** in `mime.py` where the spec asks for a guard. It is required there, not a finding.
- **`sent_at`.** Read through `message["Date"].datetime`, as long as a naive value counts as UTC and a missing or unparseable date gives `None`.
- **Connection mode.** The connection opened with `autocommit=True`, with explicit `commit()` calls, or with `with connection:` blocks, as long as each write is committed before the method returns.
- **Running migrations.** `executescript` with `BEGIN` and `COMMIT` around the migration and its `PRAGMA user_version`, or explicit `execute` calls in one transaction.
- **Mode order.** The file's mode set before or after the schema is created.
- **`add` on a duplicate.** It may also detect the conflict with a `SELECT` before the insert, as long as it calls `clock.now()` once per call and changes nothing on a conflict.
- **Extra tests.** Behaviour tests in `tests/unit/test_mime_more.py` and `tests/integration/test_store_more.py`, including ones that `monkeypatch` the email package to raise.

## 7. Verdict

Write `docs/reviews/phase-01a-parser-and-store.md` in the form `docs/phase-conventions.md` gives (`# Review: Phase 1a`), then run `.venv/bin/python scripts/check_reports.py --phase 1a`; it must print `Reports OK.`
