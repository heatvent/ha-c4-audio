"""Control4 SDDP discovery and identity mapping."""

from __future__ import annotations

import asyncio
import socket
from dataclasses import dataclass

try:
    from .const import MODEL_AMP108, MODEL_AMP16, MODEL_AMP16ZONE, MODEL_MATRIX16
except ImportError:  # running tests without the HA package
    from const import MODEL_AMP108, MODEL_AMP16, MODEL_AMP16ZONE, MODEL_MATRIX16

SDDP_MULTICAST = "239.255.255.250"
SDDP_PORT = 1902
SDDP_TIMEOUT = 2.0

AMP_HINTS = (
    "16chanamp",
    "16amp3",
    "amp108",
    "8amp",
    "c4amp",
    "matrixamp",
    "v3_16chanamp",
)
SWITCH_HINTS = ("avswitch", "avm-16", "16zams", "16s1")


@dataclass(frozen=True)
class SddpDevice:
    host: str
    ident: str
    sddp_type: str
    model_name: str
    manufacturer: str
    suggested_model: str | None


def _header_map(text: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line or line.strip().startswith(("NOTIFY", "SEARCH", "SDDP")):
            continue
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip().strip('"')
    return headers


def parse_sddp_packet(data: bytes | str, source_ip: str | None = None) -> SddpDevice | None:
    text = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else data
    headers = _header_map(text)
    from_header = headers.get("from", "")
    ip = from_header.split(":")[0].strip() if from_header else (source_ip or "")
    if not ip:
        return None
    ident = headers.get("host") or headers.get("ident") or ip
    sddp_type = headers.get("type", "")
    model_name = headers.get("model", "")
    manufacturer = headers.get("manufacturer", "")
    suggested = suggest_model(sddp_type, model_name, ident)
    if suggested is None:
        return None
    return SddpDevice(
        host=ip,
        ident=ident,
        sddp_type=sddp_type,
        model_name=model_name,
        manufacturer=manufacturer,
        suggested_model=suggested,
    )


def suggest_model(sddp_type: str, model_name: str, ident: str) -> str | None:
    blob = f"{sddp_type} {model_name} {ident}".lower()
    if any(hint in blob for hint in SWITCH_HINTS):
        return MODEL_MATRIX16
    if "amp108" in blob or "4-zone" in blob:
        return MODEL_AMP108
    if "16amp" in blob or "16chanamp" in blob or "8-zone" in blob:
        return MODEL_AMP16
    if any(hint in blob for hint in AMP_HINTS):
        return MODEL_AMP16
    return None


def identity_from_info(info: str | None, fallback: str) -> str:
    """Stable unique_id: SDDP host / c4.sy.info string, else IP."""
    text = (info or "").strip().strip('"')
    if text:
        return text.lower()
    return fallback.lower()


def _lan_ipv4() -> str:
    """Address Control4 chassis should unicast SDDP replies to (not 0.0.0.0)."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        ip = probe.getsockname()[0]
        if ip and not ip.startswith("127."):
            return ip
    except OSError:
        pass
    finally:
        probe.close()
    return "0.0.0.0"


def _sddp_search_sync(timeout: float) -> list[SddpDevice]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", 0))
    sock.settimeout(timeout)
    _bound_ip, local_port = sock.getsockname()
    local_ip = _lan_ipv4()
    payload = f'SEARCH * SDDP/1.0\r\nHost: "{local_ip}:{local_port}"\r\n\r\n'.encode("ascii")
    sock.sendto(payload, (SDDP_MULTICAST, SDDP_PORT))
    found: dict[str, SddpDevice] = {}
    try:
        while True:
            data, addr = sock.recvfrom(4096)
            parsed = parse_sddp_packet(data, addr[0])
            if parsed is None:
                continue
            found[parsed.ident.lower()] = parsed
    except TimeoutError:
        pass
    finally:
        sock.close()
    return list(found.values())


async def async_sddp_search(timeout: float = SDDP_TIMEOUT) -> list[SddpDevice]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _sddp_search_sync, timeout)
