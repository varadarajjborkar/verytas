"""Find reference photos of a named public person, so a face in content can be identified.

The creator's brief names who appears ("Riya Sen talks about the offer"). For a public figure, Wikidata
links the name to a person record and its portrait on Wikimedia Commons: structured, openly licensed,
and with a stable address to keep beside the photo. Only people (instance of human) are accepted, and the
first matching record wins: ambiguous names are left to the brand team to resolve in the library.

Nothing here decides whether the person may appear; that is the brand's record (checks/likeness.py).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import quote

import httpx

log = logging.getLogger(__name__)
WIKIDATA = "https://www.wikidata.org/w/api.php"
# Wikimedia's robot policy (https://w.wiki/4wJS): automated clients name themselves, give a contact, and
# name their HTTP library. Requests without a contact are refused with 403.
HEADERS = {"User-Agent": f"Verytas/0.1 (https://github.com/varadarajjborkar/verytas; reference photo lookup) "
                         f"httpx/{httpx.__version__}"}
HUMAN = "Q5"
MAX_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True)
class WebReference:
    name: str  # the record's own label, which may differ from how the brief spelled it
    entity: str  # Wikidata id, e.g. Q41708
    image: bytes
    media_type: str
    source_url: str  # the Commons page of the photo


async def find_portrait(name: str, *, client: httpx.AsyncClient | None = None,
                        width: int = 512) -> WebReference | None:
    """The Commons portrait of the first person on Wikidata matching `name`, or None."""
    own = client is None
    client = client or httpx.AsyncClient(timeout=15, headers=HEADERS, follow_redirects=True)
    try:
        found = (await client.get(WIKIDATA, params={
            "action": "wbsearchentities", "search": name, "language": "en", "type": "item", "limit": 5,
            "format": "json"})).json().get("search", [])
        ids = [f["id"] for f in found]
        if not ids:
            return None
        entities = (await client.get(WIKIDATA, params={
            "action": "wbgetentities", "ids": "|".join(ids), "props": "claims|labels", "languages": "en",
            "format": "json"})).json().get("entities", {})
        for qid in ids:
            claims = entities.get(qid, {}).get("claims", {})
            human = any(c["mainsnak"].get("datavalue", {}).get("value", {}).get("id") == HUMAN
                        for c in claims.get("P31", []))
            images = [c["mainsnak"].get("datavalue", {}).get("value") for c in claims.get("P18", [])]
            if not human or not images or not images[0]:
                continue
            file = images[0].replace(" ", "_")
            res = await client.get(f"https://commons.wikimedia.org/wiki/Special:FilePath/{quote(file)}",
                                   params={"width": width})
            kind = res.headers.get("content-type", "").split(";")[0]
            if res.status_code != 200 or not kind.startswith("image/") or len(res.content) > MAX_BYTES:
                continue
            label = entities[qid].get("labels", {}).get("en", {}).get("value", name)
            return WebReference(label, qid, res.content, kind,
                                f"https://commons.wikimedia.org/wiki/File:{quote(file)}")
        return None
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        log.warning("reference lookup for %r failed: %s", name, exc)
        return None
    finally:
        if own:
            await client.aclose()
