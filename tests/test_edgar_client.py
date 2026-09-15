"""Behavior tests for the daily milestone's cached SEC client."""

import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from itertools import pairwise
from threading import Thread
from unittest.mock import Mock

import pytest
import requests

from src import edgar_client as client

URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    path = tmp_path / "data" / "raw"
    monkeypatch.setattr(client, "RAW_DIR", path)
    return path


@pytest.fixture
def delays(monkeypatch):
    calls = []
    monkeypatch.setattr(time, "sleep", calls.append)
    if hasattr(client, "sleep"):
        monkeypatch.setattr(client, "sleep", calls.append)
    return calls


def response(status=200, payload=None, headers=None):
    result = requests.Response()
    result.status_code = status
    result.url = URL
    result.headers.update(headers or {})
    result._content = json.dumps({} if payload is None else payload).encode("utf-8")
    result._content_consumed = True
    return result


def cache_path(directory, url=URL):
    return directory / (hashlib.sha256(url.encode("utf-8")).hexdigest() + ".json")


def test_session_has_sec_identity():
    with client.make_session() as session:
        assert isinstance(session, requests.Session)
        assert session.headers["User-Agent"] == client.USER_AGENT
        assert "@" in session.headers["User-Agent"]


@pytest.mark.parametrize("payload", [{}, {"name": "Unicode \u00e9 \U0001f600 ' ;", "facts": []}, {"items": list(range(10001))}])
def test_fetch_caches_json_and_preserves_supplied_session(cache_dir, delays, payload):
    session = Mock(spec=requests.Session)
    session.get.return_value = response(payload=payload)
    assert client.fetch_json(URL, session) == payload
    assert json.loads(cache_path(cache_dir).read_text(encoding="utf-8")) == payload
    session.get.assert_called_once()
    assert session.get.call_args.args[0] == URL
    assert session.get.call_args.kwargs["timeout"] > 0
    assert len(delays) >= 1 and sum(delays) >= client.REQUEST_DELAY_SECONDS
    session.close.assert_not_called()


def test_cache_hit_never_creates_session_or_sleeps(cache_dir, delays, monkeypatch):
    cache_dir.mkdir(parents=True)
    cache_path(cache_dir).write_text('{"cached": true}', encoding="utf-8")
    factory = Mock(side_effect=AssertionError("cache hit must not create a session"))
    monkeypatch.setattr(client, "make_session", factory)
    assert client.fetch_json(URL) == {"cached": True}
    assert delays == []


def test_different_query_strings_have_distinct_cache_keys(cache_dir, delays):
    session = Mock(spec=requests.Session)
    session.get.side_effect = [response(payload={"id": 1}), response(payload={"id": 2})]
    for index in (1, 2):
        url = URL + f"?id={index}"
        assert client.fetch_json(url, session) == {"id": index}
        assert cache_path(cache_dir, url).exists()


@pytest.mark.parametrize("status", [429, 503])
def test_transient_errors_retry_with_exponential_polite_delay(cache_dir, delays, status):
    session = Mock(spec=requests.Session)
    attempts = []
    answers = iter([response(status), response(status), response(status), response(payload={"ok": True})])

    def get(*args, **kwargs):
        attempts.append(sum(delays))
        return next(answers)

    session.get.side_effect = get
    assert client.fetch_json(URL, session) == {"ok": True}
    assert len(attempts) == 4
    intervals = [attempts[0]] + [b - a for a, b in pairwise(attempts)]
    assert all(delay >= client.REQUEST_DELAY_SECONDS for delay in intervals)
    assert intervals[2] > intervals[1]
    assert intervals[3] > intervals[2]


@pytest.mark.parametrize("status", [429, 503])
def test_retry_exhaustion_raises_without_caching(cache_dir, delays, status):
    session = Mock(spec=requests.Session)
    session.get.return_value = response(status)
    with pytest.raises(requests.HTTPError):
        client.fetch_json(URL, session)
    assert session.get.call_count == 4
    assert not cache_path(cache_dir).exists()


@pytest.mark.parametrize("header", ["5", format_datetime(datetime.now(timezone.utc) + timedelta(seconds=120), usegmt=True)])
def test_retry_after_is_respected(cache_dir, delays, header):
    session = Mock(spec=requests.Session)
    session.get.side_effect = [response(429, headers={"Retry-After": header}), response()]
    client.fetch_json(URL, session)
    assert sum(delays) >= (5 if header == "5" else 100)


@pytest.mark.parametrize("header", ["nonsense", "-1", "Wed, 01 Jan 2020 00:00:00 GMT"])
def test_invalid_or_past_retry_after_still_uses_polite_delay(cache_dir, delays, header):
    session = Mock(spec=requests.Session)
    session.get.side_effect = [response(503, headers={"Retry-After": header}), response()]
    client.fetch_json(URL, session)
    assert all(delay >= 0 for delay in delays)
    assert sum(delays) >= 2 * client.REQUEST_DELAY_SECONDS


@pytest.mark.parametrize("status", [400, 403, 404, 500])
def test_other_http_errors_do_not_retry_or_cache(cache_dir, delays, status):
    session = Mock(spec=requests.Session)
    session.get.return_value = response(status)
    with pytest.raises(requests.HTTPError):
        client.fetch_json(URL, session)
    session.get.assert_called_once()
    assert not cache_path(cache_dir).exists()


@pytest.mark.parametrize("error", [requests.Timeout("timed out"), requests.ConnectionError("offline")])
def test_network_error_propagates_and_owned_session_closes(cache_dir, delays, monkeypatch, error):
    session = Mock(spec=requests.Session)
    session.get.side_effect = error
    monkeypatch.setattr(client, "make_session", lambda: session)
    with pytest.raises(type(error)):
        client.fetch_json(URL)
    session.close.assert_called_once()
    assert not cache_path(cache_dir).exists()


def test_owned_session_closes_on_success(cache_dir, delays, monkeypatch):
    session = Mock(spec=requests.Session)
    session.get.return_value = response()
    monkeypatch.setattr(client, "make_session", lambda: session)
    assert client.fetch_json(URL) == {}
    session.close.assert_called_once()


def test_bad_response_json_is_not_cached(cache_dir, delays):
    session = Mock(spec=requests.Session)
    result = response()
    result._content = b"not JSON"
    session.get.return_value = result
    with pytest.raises(requests.exceptions.JSONDecodeError):
        client.fetch_json(URL, session)
    assert not cache_path(cache_dir).exists()
    session.close.assert_not_called()


def test_corrupt_cache_is_reported(cache_dir, delays):
    cache_dir.mkdir(parents=True)
    cache_path(cache_dir).write_text("broken", encoding="utf-8")
    session = Mock(spec=requests.Session)
    with pytest.raises(json.JSONDecodeError):
        client.fetch_json(URL, session)
    session.get.assert_not_called()
    assert delays == []


def test_ticker_to_cik_maps_and_zero_pads_from_company_tickers_json(cache_dir, delays):
    session = Mock(spec=requests.Session)
    payload = {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        "1": {"cik_str": 789019, "ticker": "MSFT", "title": "MICROSOFT CORP"},
    }
    session.get.return_value = response(payload=payload)
    assert client.ticker_to_cik(session) == {"AAPL": "0000320193", "MSFT": "0000789019"}
    assert session.get.call_args.args[0] == client.TICKERS_URL
    assert cache_path(cache_dir, client.TICKERS_URL).exists()


def test_ticker_to_cik_second_call_hits_cache_not_network(cache_dir, delays):
    session = Mock(spec=requests.Session)
    session.get.return_value = response(payload={"0": {"cik_str": 1, "ticker": "A", "title": "A Inc"}})
    client.ticker_to_cik(session)
    client.ticker_to_cik(session)
    session.get.assert_called_once()


def test_real_http_session_retries_sends_identity_and_reuses_cache(cache_dir, delays):
    identities = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            identities.append(self.headers.get("User-Agent"))
            self.send_response(503 if len(identities) == 1 else 200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"source": "local fixture"}')

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/facts"
        assert client.fetch_json(url) == {"source": "local fixture"}
        assert client.fetch_json(url) == {"source": "local fixture"}
        assert identities == [client.USER_AGENT, client.USER_AGENT]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
