#!/usr/bin/env python3
"""Turn one Word or PowerPoint file into a PDF, for page previews. Run by verytas-convert@.service, one
process per connection on /run/verytas-convert.sock, with no network, no view of /srv/verytas, a throwaway
user and hard limits (see the unit). The API has already cut every reference to anything outside the file.

Wire format, both ways binary on the socket:
  request:  b"docx\n" or b"pptx\n", then an 8-byte big-endian length, then the file
  response: b"OK\n" + 8-byte length + the PDF, or b"ERR <reason>\n"
Standard library only, so it runs on the system Python.
"""

from __future__ import annotations

import os
import signal
import struct
import subprocess
import sys
import tempfile

MAX_IN = 25 * 1024 * 1024
SECONDS = 90
FILTERS = {
    "docx": "pdf",
    "pptx": 'pdf:impress_pdf_Export:{"ExportHiddenSlides":{"type":"boolean","value":"true"}}',
}
SETTINGS = [
    ("/org.openoffice.Inet/Settings", "ooInetProxyType", "2"),
    *[("/org.openoffice.Inet/Settings", f"ooInet{kind}Proxy{field}", value)
      for kind in ("HTTP", "HTTPS", "FTP") for field, value in (("Name", "127.0.0.1"), ("Port", "9"))],
    ("/org.openoffice.Office.Common/Security/Scripting", "MacroSecurityLevel", "3"),
    ("/org.openoffice.Office.Common/Security/Scripting", "DisableMacrosExecution", "true"),
    ("/org.openoffice.Office.Writer/Content/Update", "Link", "2"),
]


PROFILE = ('<?xml version="1.0" encoding="UTF-8"?>\n<oor:items xmlns:oor="http://openoffice.org/2001/registry" '
           'xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">\n'
           + "".join(f'<item oor:path="{p}"><prop oor:name="{n}" oor:op="fuse"><value>{v}</value></prop></item>\n'
                     for p, n, v in SETTINGS)
           + "</oor:items>\n")


def read_exact(stream, n: int) -> bytes:
    out = b""
    while len(out) < n:
        chunk = stream.read(n - len(out))
        if not chunk:
            raise ValueError("short read")
        out += chunk
    return out


def fail(reason: str) -> None:
    sys.stdout.buffer.write(b"ERR " + reason.encode()[:200] + b"\n")
    sys.stdout.buffer.flush()


def main() -> None:
    inp = sys.stdin.buffer
    kind = inp.readline(16).strip().decode("ascii", "replace")
    if kind not in FILTERS:
        return fail("unknown kind")
    (size,) = struct.unpack(">Q", read_exact(inp, 8))
    if size > MAX_IN:
        return fail("too large")
    data = read_exact(inp, size)
    with tempfile.TemporaryDirectory(prefix="convert-") as tmp:
        user = os.path.join(tmp, "profile", "user")
        os.makedirs(user)
        with open(os.path.join(user, "registrymodifications.xcu"), "w") as fh:
            fh.write(PROFILE)
        src = os.path.join(tmp, "file." + kind)
        with open(src, "wb") as fh:
            fh.write(data)
        proc = subprocess.Popen(
            ["/usr/bin/soffice", "--headless", "--norestore", "--nolockcheck", "--nodefault", "--nologo",
             f"-env:UserInstallation=file://{tmp}/profile", "--convert-to", FILTERS[kind], "--outdir", tmp, src],
            cwd=tmp, env={"HOME": tmp, "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, start_new_session=True)
        try:
            _, err = proc.communicate(timeout=SECONDS)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
            return fail("timed out")
        out = os.path.join(tmp, "file.pdf")
        if not os.path.exists(out):
            sys.stderr.write((err or b"")[-500:].decode("utf-8", "replace"))
            return fail("conversion failed")
        with open(out, "rb") as fh:
            pdf = fh.read()
    sys.stdout.buffer.write(b"OK\n" + struct.pack(">Q", len(pdf)) + pdf)
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001, the caller gets a reason, never a hang
        fail(type(exc).__name__)
