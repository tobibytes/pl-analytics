"""The disk cache, including the behaviour that matters when a source is down."""

import football.cache as cache_module
from football.cache import cached, clear


def test_second_call_does_not_refetch(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_module, "CACHE_DIR", tmp_path)
    calls = []

    def fetch():
        calls.append(1)
        return {"value": len(calls)}

    assert cached("src", "key", fetch) == {"value": 1}
    assert cached("src", "key", fetch) == {"value": 1}
    assert len(calls) == 1


def test_stale_entry_beats_an_error(tmp_path, monkeypatch):
    """An old chart is better than no chart -- these sources go down."""
    monkeypatch.setattr(cache_module, "CACHE_DIR", tmp_path)
    cached("src", "key", lambda: {"value": "fresh"})

    def broken():
        raise ConnectionError("understat is down")

    assert cached("src", "key", broken, max_age=0) == {"value": "fresh"}


def test_error_propagates_when_nothing_is_cached(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_module, "CACHE_DIR", tmp_path)

    def broken():
        raise ConnectionError("understat is down")

    try:
        cached("src", "missing", broken)
    except ConnectionError:
        pass
    else:
        raise AssertionError("expected the error to propagate")


def test_clear_counts_what_it_removed(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_module, "CACHE_DIR", tmp_path)
    cached("a", "one", lambda: 1)
    cached("a", "two", lambda: 2)
    cached("b", "three", lambda: 3)
    assert clear("a") == 2
    assert clear() == 1


def test_keys_with_slashes_do_not_escape_the_cache_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_module, "CACHE_DIR", tmp_path)
    cached("src", "../../etc/passwd", lambda: "safe")
    written = list(tmp_path.rglob("*.json"))
    assert len(written) == 1
    assert tmp_path in written[0].parents
