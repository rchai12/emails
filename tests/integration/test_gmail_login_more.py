import threading

import httpx
import pytest

from mailroom.gmail_login import Callback, LoginError, new_http
from tests.fakes import FakeGmail
from tests.integration.test_gmail_login import SCOPE, exchange, granted


def test_a_post_to_the_callback_is_ignored(capsys: pytest.CaptureFixture[str]) -> None:
    with Callback("personal") as callback:
        responses: list[httpx.Response] = []

        def run() -> None:
            responses.append(httpx.post(f"{callback.redirect_uri}/?code=secret-code", timeout=5))
            responses.append(
                httpx.get(f"{callback.redirect_uri}/?state=state-1&code=code-1", timeout=5)
            )

        thread = threading.Thread(target=run)
        thread.start()
        assert callback.wait("state-1") == "code-1"
    thread.join()
    assert [response.status_code for response in responses] == [501, 200]
    assert "secret-code" not in responses[0].text
    assert capsys.readouterr() == ("", "")


def test_a_token_scope_that_is_not_text_is_rejected() -> None:
    fake = FakeGmail()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"refresh_token": "refresh-1", "scope": [SCOPE]})

    with pytest.raises(LoginError) as caught:
        exchange(fake, granted(fake), handler)
    assert str(caught.value) == "gmail login failed: personal (response)"
    assert "refresh-1" not in str(caught.value)


def test_new_http_ignores_proxy_settings_and_times_out() -> None:
    client = new_http()
    assert client.timeout == httpx.Timeout(30.0)
    assert client.trust_env is False
    assert client.follow_redirects is False
