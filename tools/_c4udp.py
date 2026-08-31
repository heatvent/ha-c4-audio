"""Minimal UDP helper so the test tools run without Home Assistant."""

from __future__ import annotations

import socket
from dataclasses import dataclass


def build_frame(prefix: str, sequence: int, body: str) -> bytes:
    return f"{prefix}{sequence & 0xFFFF:04x} {body.strip()}\r\n".encode("ascii")


@dataclass
class Parsed:
    kind: str
    sequence: int | None
    status: str | None
    command: str | None
    args: list[str]
    raw: str


def parse_packet(data: bytes) -> Parsed:
    text = data.decode("utf-8", errors="replace").strip()
    parts = text.split()
    if not parts:
        return Parsed("other", None, None, None, [], text)
    header = parts[0]
    tag = header[:2]
    seq = None
    if len(header) > 2:
        try:
            seq = int(header[2:], 16)
        except ValueError:
            seq = None
    if tag == "0r":
        rest = parts[1:]
        status = rest[0] if rest else None
        cmd = rest[1] if len(rest) > 1 and rest[1].startswith("c4.") else None
        args = rest[2:] if cmd else rest[1:]
        return Parsed("reply", seq, status, cmd, args, text)
    if tag == "0t":
        rest = parts[1:]
        if rest and rest[0] in {"sa", "nsa"}:
            rest = rest[1:]
        cmd = rest[0] if rest else None
        return Parsed("status", seq, None, cmd, rest[1:] if rest else [], text)
    return Parsed("other", seq, None, None, parts[1:], text)


def is_get_body(body: str) -> bool:
    body = body.strip()
    if body.startswith(("0s ", "0g ", "0s", "0g")) and body[0:2] in {"0s", "0g"}:
        return False
    gets = {
        "c4.sy.fwv",
        "c4.sy.afwv",
        "c4.amp.psave",
        "c4.amp.ain",
        "c4.amp.avol",
        "c4.amp.amut",
        "c4.amp.vlim",
        "c4.amp.abss",
        "c4.amp.atrb",
        "c4.amp.abal",
    }
    if body in gets:
        return True
    if body.startswith(("c4.amp.digi", "c4.amp.igain")):
        return " " not in body[12:].strip() or body.startswith("c4.amp.digi") and body.count(" ") == 1
    return False


def send_and_collect(
    host: str,
    port: int,
    prefix: str,
    sequence: int,
    body: str,
    timeout: float,
    extra_listen: float = 0.4,
) -> list[Parsed]:
    frame = build_frame(prefix, sequence, body)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    packets: list[Parsed] = []
    try:
        sock.sendto(frame, (host, port))
        deadline = timeout
        sock.settimeout(deadline)
        try:
            while True:
                data, _addr = sock.recvfrom(2048)
                packets.append(parse_packet(data))
                sock.settimeout(extra_listen)
        except TimeoutError:
            pass
        except socket.timeout:
            pass
    finally:
        sock.close()
    return packets, frame
