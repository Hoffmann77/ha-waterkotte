"""Tests for the EcoTouch bridge (the requests to the web interface of the heat pump)."""
from contextlib import asynccontextmanager

import pytest

from custom_components.waterkotte_heatpump.pywaterkotte_ha import EcotouchBridge
from custom_components.waterkotte_heatpump.pywaterkotte_ha.error import StatusException, TooManyUsersException
from custom_components.waterkotte_heatpump.pywaterkotte_ha.tags import WKHPTag


class FakeResponse:
    def __init__(self, status: int, content: str):
        self.status = status
        self._content = content
        self.url = "http://heatpump"
        self.cookies = {}

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    async def text(self):
        return self._content


class FakeSession:
    """Returns the queued responses per path ('/cgi/readTags', ...) - and records the requested tags."""

    def __init__(self, responses: dict[str, list[FakeResponse]]):
        self.responses = responses
        self.requests = []

    @asynccontextmanager
    async def get(self, url: str, params=None, **kwargs):
        path = url[url.index("/cgi/"):]
        self.requests.append((path, [value for key, value in (params or {}).items() if key.startswith("t")]))
        yield self.responses[path].pop(0)


def _tag_response(*tags: str) -> FakeResponse:
    return FakeResponse(200, "".join(f"#{tag}\tS_OK\n192\t1\n" for tag in tags))


def _bridge(session: FakeSession, tags_per_request: int = 75) -> EcotouchBridge:
    bridge = EcotouchBridge(host="heatpump", web_session=session, tags_per_request=tags_per_request)
    bridge.auth_cookies = {"IDALToken": "token"}
    return bridge


async def test_too_many_users() -> None:
    session = FakeSession({"/cgi/readTags": [FakeResponse(200, "#E_TOO_MANY_USERS\n")]})
    with pytest.raises(TooManyUsersException):
        await _bridge(session).read_values([WKHPTag.TEMPERATURE_OUTSIDE])

    session = FakeSession({"/cgi/writeTags": [FakeResponse(200, "#E_TOO_MANY_USERS\n")]})
    with pytest.raises(TooManyUsersException):
        await _bridge(session).write_value(WKHPTag.HOLIDAY_ENABLED, True)


async def test_need_login_retries_once() -> None:
    """Test that the bridge logs in again, when the session expired - but only once."""
    tag = WKHPTag.TEMPERATURE_OUTSIDE.tags[0]
    session = FakeSession({
        "/cgi/readTags": [FakeResponse(200, "#E_NEED_LOGIN\n"), _tag_response(tag)],
        "/cgi/login": [FakeResponse(200, "#S_OK\n")],
    })
    result = await _bridge(session).read_values([WKHPTag.TEMPERATURE_OUTSIDE])
    assert result[WKHPTag.TEMPERATURE_OUTSIDE]["status"] == "S_OK"

    session = FakeSession({
        "/cgi/readTags": [FakeResponse(200, "#E_NEED_LOGIN\n"), FakeResponse(200, "#E_NEED_LOGIN\n")],
        "/cgi/login": [FakeResponse(200, "#S_OK\n")],
    })
    with pytest.raises(StatusException):
        await _bridge(session).read_values([WKHPTag.TEMPERATURE_OUTSIDE])


async def test_http_500_keeps_previous_results() -> None:
    """Test that a retry after an HTTP 500 keeps the values of the previous requests (chunks)."""
    first, second = WKHPTag.TEMPERATURE_OUTSIDE.tags[0], WKHPTag.TEMPERATURE_RETURN.tags[0]
    session = FakeSession({
        "/cgi/readTags": [_tag_response(first), FakeResponse(500, ""), _tag_response(second)],
        "/cgi/login": [FakeResponse(200, "#S_OK\n")],
    })
    values, states = await _bridge(session, tags_per_request=1)._read_tags([first, second])
    assert values == {first: "1", second: "1"}
    assert states == {first: "S_OK", second: "S_OK"}


async def test_http_500_retries_only_once() -> None:
    tag = WKHPTag.TEMPERATURE_OUTSIDE.tags[0]
    session = FakeSession({
        "/cgi/readTags": [FakeResponse(500, ""), FakeResponse(500, "")],
        "/cgi/login": [FakeResponse(200, "#S_OK\n")],
    })
    assert await _bridge(session)._read_tags([tag]) == ({}, {})


async def test_missing_tag_is_no_error() -> None:
    """Test that a missing value of a tag does not affect the values of the other tags."""
    tag = WKHPTag.TEMPERATURE_OUTSIDE.tags[0]
    session = FakeSession({"/cgi/readTags": [_tag_response(tag)]})
    bridge = _bridge(session)
    # the second tag is not part of the parsed values (e.g. the request for its chunk failed)
    bridge._read_tags = _fake_read_tags({tag: "10"})

    result = await bridge.read_values([WKHPTag.TEMPERATURE_RETURN, WKHPTag.TEMPERATURE_OUTSIDE])
    assert WKHPTag.TEMPERATURE_RETURN not in result
    assert result[WKHPTag.TEMPERATURE_OUTSIDE]["value"] == 1.0


def _fake_read_tags(values: dict):
    async def read_tags(tags, *args, **kwargs):
        return dict(values), {tag: "S_OK" for tag in values}
    return read_tags
