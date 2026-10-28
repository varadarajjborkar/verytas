"""Every route meets bad input with a 4xx, never a 500.

Walks the app's own route table, so a route added later is covered without anyone remembering to add
it here. Each one gets the ids nobody has (zero, negative, past 64 bits, words), the bodies nobody
sends (wrong types, empty, nested junk, a megabyte of text) and the query strings nobody types, from
each role. A 500 means an unhandled path: the person sees "something went wrong" instead of a reason.
"""

from __future__ import annotations

import re

import pytest

from tests.test_media import _auth, world  # noqa: F401  (the fixture is used by name)

# Long-lived streams would hold the test open; they have their own tests.
SKIP = re.compile(r"/stream$|^/mcp")
IDS = ["0", "-1", "99999999999999999999999", "abc", "%00", "1e9"]
BODIES = [None, {}, [], "x", {"name": None, "body": 12, "id": "drop table"},
          {"body": "x" * 1_000_000}, {"a": {"b": {"c": [1, {"d": None}]}}}]


def _routes(app):
    # The OpenAPI schema, not app.routes: included routers are nested objects in newer FastAPI.
    for path, ops in app.openapi()["paths"].items():
        if not SKIP.search(path):
            for method in ops:
                if method.upper() in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                    yield method.upper(), path


def _fill(path: str, value: str) -> str:
    return re.sub(r"\{[^}]+\}", value, path)


@pytest.mark.parametrize("who", ["admin", "creator"])
def test_no_route_answers_bad_input_with_a_server_error(client, world, who):  # noqa: F811
    failures = []
    routes = list(_routes(client.app))
    assert len(routes) > 100, "the sweep should see the whole API"
    for method, path in routes:
        for ident in IDS:
            url = _fill(path, ident)
            for body in BODIES if method in ("POST", "PUT", "PATCH") else [None]:
                kwargs = {"headers": _auth(world[who])}
                if body is not None:
                    kwargs["json"] = body
                try:
                    res = client.request(method, url, **kwargs)
                except Exception as exc:  # an exception that escapes the app is the same failure as a 500
                    failures.append(f"{method} {url} {str(body)[:40]}: raised {type(exc).__name__}: {exc}"[:200])
                    continue
                if res.status_code >= 500:
                    failures.append(f"{method} {url} {str(body)[:40]}: {res.status_code} {res.text[:80]}")
    assert not failures, "\n".join(sorted(set(failures))[:40])


def test_odd_query_strings_are_refused_cleanly(client, world):  # noqa: F811
    failures = []
    for method, path in _routes(client.app):
        if method != "GET" or "{" in path:
            continue
        for qs in ("limit=-5", "limit=999999999", "offset=abc", "status=nope", "q=" + "%" * 300, "since=not-a-date"):
            res = client.get(f"{path}?{qs}", headers=_auth(world["admin"]))
            if res.status_code >= 500:
                failures.append(f"GET {path}?{qs[:30]}: {res.status_code}")
    assert not failures, "\n".join(failures[:40])
