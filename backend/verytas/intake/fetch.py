"""Reading a live source: one HTTPS link to a CSV, JSON or spreadsheet, fetched read-only and safely.

A link a company registers is fetched by our server, so it must not be a way into our own network
(server-side request forgery). The host is resolved once, every address it resolves to must be a public
one (no private, loopback, link-local or cloud-metadata address, in IPv4 or IPv6 form), and the request
then goes to that pinned address, with TLS still verified against the hostname. Resolving twice, once
to check and once to connect, is the DNS-rebinding hole behind several recent advisories. Redirects are
not followed, the body is capped, and only data formats are accepted.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse, urlunparse

import httpx

MAX_BYTES = 10 * 1024 * 1024
TIMEOUT_S = 20.0
_TYPES = ("text/csv", "text/plain", "application/json", "text/tab-separated-values",
          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/octet-stream")


class FetchRefused(Exception):
    """The link may not be fetched, or did not give back data; the message says why, for the admin."""


def check_url(url: str) -> tuple[str, str, int]:
    u = urlparse(url.strip())
    if u.scheme != "https":
        raise FetchRefused("only https links can be read")
    if not u.hostname or u.username or u.password:
        raise FetchRefused("the link needs a host name and no password in it")
    return url.strip(), u.hostname, u.port or 443


_NOT_PUBLIC = (ipaddress.ip_network("64:ff9b::/96"), ipaddress.ip_network("64:ff9b:1::/48"),
               ipaddress.ip_network("fec0::/10"))


async def _public_address(host: str, port: int) -> str:
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise FetchRefused(f"{host} could not be found") from exc
    addresses = {info[4][0] for info in infos}
    for a in addresses:
        ip = ipaddress.ip_address(a.split("%")[0])
        mapped = getattr(ip, "ipv4_mapped", None)
        # NAT64 and site-local addresses count as global to ipaddress but can reach inside where a gateway
        # translates them, so they are refused outright.
        if not ip.is_global or (mapped is not None and not mapped.is_global) or any(
                ip in net for net in _NOT_PUBLIC if net.version == ip.version):
            raise FetchRefused(f"{host} points inside a private network; only public sources can be read")
    if not addresses:
        raise FetchRefused(f"{host} could not be found")
    return sorted(addresses)[0]


async def fetch(url: str) -> tuple[bytes, str]:
    """The body and its declared type. Raises FetchRefused with a plain reason."""
    url, host, port = check_url(url)
    ip = await _public_address(host, port)
    u = urlparse(url)
    netloc = f"[{ip}]" if ":" in ip else ip
    pinned = urlunparse(u._replace(netloc=f"{netloc}:{port}"))
    host_header = host if port == 443 else f"{host}:{port}"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S, follow_redirects=False) as client, client.stream(
                "GET", pinned, headers={"Host": host_header, "Accept": "text/csv, application/json, */*;q=0.5"},
                extensions={"sni_hostname": host}) as res:
            if res.is_redirect:
                raise FetchRefused("the link redirects; use the final address")
            if res.status_code != 200:
                raise FetchRefused(f"the source answered HTTP {res.status_code}")
            kind = res.headers.get("content-type", "").split(";")[0].strip().lower()
            if kind and not kind.startswith(_TYPES):
                raise FetchRefused(f"the source sent {kind}, not data (CSV, JSON or a spreadsheet)")
            body = bytearray()
            async for chunk in res.aiter_bytes():
                body += chunk
                if len(body) > MAX_BYTES:
                    raise FetchRefused("the source is over 10 MB")
    except httpx.HTTPError as exc:
        raise FetchRefused(f"the source could not be read ({type(exc).__name__})") from exc
    return bytes(body), kind
