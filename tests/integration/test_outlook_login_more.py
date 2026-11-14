"""The Outlook login client ignores proxy settings and does not follow redirects."""

import httpx

from mailroom.outlook_login import new_http


def test_new_http_ignores_proxy_settings_and_times_out() -> None:
    client = new_http()
    assert client.timeout == httpx.Timeout(30.0)
    assert client.trust_env is False
    assert client.follow_redirects is False
