"""Start the stopped vision worker instance and wait until it answers.

The worker stops itself after 20 idle minutes (deploy/vision.sh), so most of the time it costs nothing.
The first review that needs it starts it here: EC2 StartInstances with the API server's own instance role
(credentials from the instance metadata service, never stored), then the worker's /health is polled until
it answers. A review waits up to `timeout_s`; past that the character check is reported as not run.

Signed with AWS Signature Version 4 by hand: it is one request type, and botocore would add 80 MB to the
API servers for it.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import hmac
import time
from dataclasses import dataclass
from urllib.parse import quote

import httpx

IMDS = "http://169.254.169.254"
EC2_VERSION = "2016-11-15"


@dataclass(frozen=True)
class Credentials:
    key: str
    secret: str
    token: str | None = None


async def instance_credentials(client: httpx.AsyncClient) -> tuple[Credentials, str]:
    """The instance role's temporary credentials and the region, via IMDSv2."""
    async def text(res: httpx.Response) -> str:
        if res.status_code != 200 or not res.text.strip():
            raise httpx.HTTPError(f"instance metadata answered {res.status_code} for {res.url.path}")
        return res.text.strip()

    token = await text(await client.put(f"{IMDS}/latest/api/token",
                                        headers={"X-aws-ec2-metadata-token-ttl-seconds": "300"}))
    h = {"X-aws-ec2-metadata-token": token}
    # No role attached answers 404 here, which reads as "can't wake", not a crash.
    role = (await text(await client.get(f"{IMDS}/latest/meta-data/iam/security-credentials/", headers=h))).split()[0]
    creds = (await client.get(f"{IMDS}/latest/meta-data/iam/security-credentials/{role}", headers=h)).json()
    region = await text(await client.get(f"{IMDS}/latest/meta-data/placement/region", headers=h))
    try:
        return Credentials(creds["AccessKeyId"], creds["SecretAccessKey"], creds.get("Token")), region
    except (KeyError, TypeError) as exc:
        raise httpx.HTTPError("instance metadata gave no usable credentials") from exc


def signed(creds: Credentials, region: str, params: dict[str, str],
           now: dt.datetime | None = None) -> tuple[str, dict[str, str], str]:
    """(url, headers, body) for an EC2 Query API POST, signed with SigV4."""
    now = now or dt.datetime.now(dt.UTC)
    amz_date, day = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    host = f"ec2.{region}.amazonaws.com"
    body = "&".join(f"{quote(k, safe='')}={quote(v, safe='')}" for k, v in sorted(params.items()))
    headers = {"content-type": "application/x-www-form-urlencoded; charset=utf-8", "host": host,
               "x-amz-date": amz_date}
    if creds.token:
        headers["x-amz-security-token"] = creds.token
    names = sorted(headers)
    canonical = "\n".join(["POST", "/", "", *(f"{n}:{headers[n]}" for n in names), "", ";".join(names),
                           hashlib.sha256(body.encode()).hexdigest()])
    scope = f"{day}/{region}/ec2/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    key = f"AWS4{creds.secret}".encode()
    for part in (day, region, "ec2", "aws4_request"):
        key = hmac.new(key, part.encode(), hashlib.sha256).digest()
    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    headers["authorization"] = (f"AWS4-HMAC-SHA256 Credential={creds.key}/{scope}, "
                                f"SignedHeaders={';'.join(names)}, Signature={signature}")
    return f"https://{host}/", headers, body


# After a failed wake, reviews within this long don't try again: each would wait out the whole timeout.
RETRY_AFTER_S = 120.0


class Waker:
    """Starts one worker instance at most once at a time; concurrent reviews wait on the same start."""

    def __init__(self, instance_id: str, health_url: str, timeout_s: float = 240.0) -> None:
        self.instance_id, self.health_url, self.timeout_s = instance_id, health_url, timeout_s
        self._lock = asyncio.Lock()
        self._failed_at = -RETRY_AFTER_S

    async def __call__(self) -> None:
        async with self._lock:
            if time.monotonic() - self._failed_at < RETRY_AFTER_S:
                raise httpx.HTTPError("the vision worker failed to wake moments ago; not retrying yet")
            try:
                await self._wake()
            except httpx.HTTPError:
                self._failed_at = time.monotonic()
                raise

    async def _wake(self) -> None:
        async with httpx.AsyncClient(timeout=10) as client:
            if await self._healthy(client):
                return  # another review already woke it
            creds, region = await instance_credentials(client)
            deadline = time.monotonic() + self.timeout_s
            started = False
            while time.monotonic() < deadline:
                if not started:
                    url, headers, body = signed(creds, region, {"Action": "StartInstances", "Version": EC2_VERSION,
                                                                "InstanceId.1": self.instance_id})
                    res = await client.post(url, headers=headers, content=body)
                    if res.status_code == 200:
                        started = True
                    elif "IncorrectInstanceState" not in res.text:
                        raise httpx.HTTPError(f"StartInstances answered {res.status_code}")
                    # Still stopping from its last idle stop: it can be started once it has stopped.
                elif await self._healthy(client):
                    return
                await asyncio.sleep(5)
        raise httpx.TimeoutException(f"the vision worker did not wake within {self.timeout_s:.0f} s")

    async def _healthy(self, client: httpx.AsyncClient) -> bool:
        try:
            return (await client.get(self.health_url, timeout=3)).status_code == 200
        except httpx.HTTPError:
            return False
