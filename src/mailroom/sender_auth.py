import re
from dataclasses import dataclass

from mailroom.record import Record

_DOMAIN = re.compile(r"[^@]+@([^@]+)")

AUTHSERV_IDS: dict[str, str] = {"gmail": "mx.google.com"}


@dataclass(frozen=True)
class AuthResult:
    method: str
    result: str
    props: tuple[tuple[str, str], ...]


def _without_comments(header: str) -> str | None:
    depth = 0
    kept: list[str] = []
    for character in header:
        if character == "(":
            depth += 1
        elif character == ")":
            if depth == 0:
                return None
            depth -= 1
        elif depth == 0:
            kept.append(character)
    if depth != 0:
        return None
    return "".join(kept)


def _prop(result: AuthResult, key: str) -> str | None:
    for name, value in result.props:
        if name == key:
            return value
    return None


def _aligned(value: str, domain: str) -> bool:
    candidate = value.lower()
    expected = domain.lower()
    return candidate == expected or candidate.endswith("." + expected)


def _mailfrom_domain(value: str) -> str:
    if "@" not in value:
        return value
    return value.rsplit("@", 1)[1]


def _dkim_domain(result: AuthResult) -> str | None:
    header_d = _prop(result, "header.d")
    if header_d is not None:
        return header_d
    header_i = _prop(result, "header.i")
    if header_i is None or "@" not in header_i:
        return None
    return header_i.rsplit("@", 1)[1]


def _sender_domain(sender: str) -> str | None:
    match = _DOMAIN.fullmatch(sender)
    if match is None:
        return None
    return match.group(1)


def _method_passes(results: tuple[AuthResult, ...], method: str, prop: str, domain: str) -> bool:
    for result in results:
        if result.method != method or result.result != "pass":
            continue
        if method == "dkim":
            found = _dkim_domain(result)
        else:
            value = _prop(result, prop)
            found = None if value is None else _mailfrom_domain(value)
        if found is not None and _aligned(found, domain):
            return True
    return False


def _dmarc_passes(results: tuple[AuthResult, ...], domain: str) -> bool:
    expected = domain.lower()
    for result in results:
        if result.method != "dmarc" or result.result != "pass":
            continue
        header_from = _prop(result, "header.from")
        if header_from is not None and header_from.lower() == expected:
            return True
    return False


def parse_results(header: str) -> tuple[str, tuple[AuthResult, ...]]:
    readable = _without_comments(header)
    if readable is None:
        return "", ()
    parts = readable.split(";")
    words = parts[0].split()
    authserv_id = words[0].lower() if words else ""
    results: list[AuthResult] = []
    for part in parts[1:]:
        tokens = part.split()
        if not tokens:
            continue
        method, separator, result = tokens[0].partition("=")
        if separator == "" or method == "" or result == "":
            continue
        props = tuple(
            (token.split("=", 1)[0].lower(), token.split("=", 1)[1])
            for token in tokens[1:]
            if "=" in token
        )
        results.append(AuthResult(method.lower(), result.lower(), props))
    return authserv_id, tuple(results)


def _method_word(word: str) -> bool:
    method, separator, result = word.partition("=")
    return separator != "" and method != "" and result != ""


def _leading_result(header: str) -> AuthResult | None:
    readable = _without_comments(header)
    if readable is None:
        return None
    tokens = readable.split(";", 1)[0].split()
    if not tokens or not _method_word(tokens[0]):
        return None
    method, _, result = tokens[0].partition("=")
    props = tuple(
        (token.split("=", 1)[0].lower(), token.split("=", 1)[1])
        for token in tokens[1:]
        if "=" in token
    )
    return AuthResult(method.lower(), result.lower(), props)


def _outlook_verified(record: Record) -> bool:
    if not record.authentication_results:
        return False
    leading = _leading_result(record.authentication_results[0])
    if leading is None:
        return False
    _, rest = parse_results(record.authentication_results[0])
    results = (leading, *rest)
    if not any(item.method == "compauth" for item in results):
        return False
    domain = _sender_domain(record.sender)
    if domain is None:
        return False
    return _dmarc_passes(results, domain) or (
        _method_passes(results, "spf", "smtp.mailfrom", domain)
        and _method_passes(results, "dkim", "header.d", domain)
    )


def verified(record: Record) -> bool:
    if record.provider == "outlook":
        return _outlook_verified(record)
    expected = AUTHSERV_IDS.get(record.provider)
    if expected is None or not record.authentication_results:
        return False
    domain = _sender_domain(record.sender)
    if domain is None:
        return False
    authserv_id, results = parse_results(record.authentication_results[0])
    if authserv_id != expected:
        return False
    return _dmarc_passes(results, domain) or (
        _method_passes(results, "spf", "smtp.mailfrom", domain)
        and _method_passes(results, "dkim", "header.d", domain)
    )
