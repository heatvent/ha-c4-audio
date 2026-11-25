"""Async UDP client with sequence matching for Control4 audio devices."""

from __future__ import annotations

import asyncio
import logging
import socket
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from .const import GET_RETRIES, REJECTED
from .protocol import ParsedPacket, build_frame, next_sequence, parse_packet

_LOGGER = logging.getLogger(__name__)

ACTIVITY_MAX = 20


def _ascii_frame(data: bytes | str) -> str:
    if isinstance(data, bytes):
        return data.decode("ascii", "replace").rstrip("\r\n")
    return str(data).rstrip("\r\n")


def _stamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


class C4UdpProtocol(asyncio.DatagramProtocol):
    def __init__(
        self,
        on_packet: Callable[[ParsedPacket], None],
        on_unparsed: Callable[[bytes, object], None] | None = None,
        on_lost: Callable[[], None] | None = None,
    ) -> None:
        self._on_packet = on_packet
        self._on_unparsed = on_unparsed
        self._on_lost = on_lost

    def datagram_received(self, data: bytes, addr) -> None:  # noqa: ANN001
        parsed = parse_packet(data)
        if parsed is None:
            if self._on_unparsed is not None:
                self._on_unparsed(data, addr)
            else:
                _LOGGER.warning("UDP from %s ignored (unparsed): %r", addr, data[:120])
            return
        _LOGGER.debug("UDP from %s: %s", addr, parsed.raw)
        self._on_packet(parsed)

    def error_received(self, exc: Exception) -> None:
        _LOGGER.warning("UDP error: %s", exc)
        if self._on_lost is not None:
            self._on_lost()

    def connection_lost(self, exc: Exception | None) -> None:
        if exc is not None:
            _LOGGER.warning("UDP connection lost: %s", exc)
        if self._on_lost is not None:
            self._on_lost()


class C4UdpClient:
    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self._transport: asyncio.DatagramTransport | None = None
        self._seq = 0x1000
        self._pending: dict[int, asyncio.Future[ParsedPacket]] = {}
        self._pending_noisy: dict[int, bool] = {}
        self._listeners: list[Callable[[ParsedPacket], None]] = []
        self._activity_listeners: list[Callable[[], None]] = []
        self._activity: deque[str] = deque(maxlen=ACTIVITY_MAX)
        self._lock = asyncio.Lock()
        self._closing = False
        self._dropping = False

    def add_listener(self, callback: Callable[[ParsedPacket], None]) -> None:
        self._listeners.append(callback)

    def add_activity_listener(self, callback: Callable[[], None]) -> None:
        self._activity_listeners.append(callback)

    @property
    def activity_lines(self) -> list[str]:
        return list(self._activity)

    def _note(self, line: str, *, noisy: bool) -> None:
        if noisy:
            self._activity.append(line)
            _LOGGER.debug("%s", line)
            for callback in self._activity_listeners:
                try:
                    callback()
                except Exception:  # noqa: BLE001 — keep the socket loop alive
                    _LOGGER.exception("Error in UDP activity listener")
        else:
            _LOGGER.debug("%s", line)

    def _unparsed(self, data: bytes, addr) -> None:  # noqa: ANN001
        preview = _ascii_frame(data)[:160]
        self._note(f"{_stamp()}  ←  {self.host}  unparsed: {preview}", noisy=True)
        _LOGGER.warning("UDP from %s ignored (unparsed): %r", addr, data[:120])

    async def _open_socket(self) -> None:
        loop = asyncio.get_running_loop()
        transport, _protocol = await loop.create_datagram_endpoint(
            lambda: C4UdpProtocol(self._handle_packet, self._unparsed, self._socket_lost),
            remote_addr=(self.host, self.port),
            family=socket.AF_INET,
        )
        self._transport = transport
        self._closing = False

    def _drop_socket(self, *, cancel: bool) -> None:
        if self._dropping:
            return
        self._dropping = True
        try:
            transport = self._transport
            self._transport = None
            pending = list(self._pending.values())
            self._pending.clear()
            self._pending_noisy.clear()
            if transport is not None:
                transport.close()
            for future in pending:
                if future.done():
                    continue
                if cancel:
                    future.cancel()
                else:
                    future.set_exception(ConnectionError("Control4 UDP socket closed"))
        finally:
            self._dropping = False

    def _socket_lost(self) -> None:
        if self._closing:
            return
        self._drop_socket(cancel=False)

    async def async_start(self) -> None:
        async with self._lock:
            if self._transport is None:
                await self._open_socket()

    async def async_stop(self) -> None:
        async with self._lock:
            self._closing = True
            self._drop_socket(cancel=True)

    def _handle_packet(self, packet: ParsedPacket) -> None:
        if packet.kind == "reply" and packet.sequence in self._pending:
            future = self._pending.pop(packet.sequence)
            noisy = self._pending_noisy.pop(packet.sequence, False)
            self._note(f"{_stamp()}  ←  {self.host}  {packet.raw}", noisy=noisy)
            if not future.done():
                future.set_result(packet)
        elif packet.kind == "status":
            self._note(f"{_stamp()}  ←  {self.host}  {packet.raw}", noisy=True)
        for listener in self._listeners:
            try:
                listener(packet)
            except Exception:  # noqa: BLE001 — keep the socket loop alive
                _LOGGER.exception("Error in UDP listener")

    async def async_send(self, prefix: str, body: str, *, retries: int = 0) -> ParsedPacket | None:
        """Send one frame and wait for its reply. Repeat it up to `retries` times if none comes.

        A repeated SET keeps the lock, so it can never land after a newer command.
        A repeated GET lets waiting commands go first.
        """
        if prefix.startswith("0g"):
            for _attempt in range(retries + 1):
                async with self._lock:
                    packet = await self._async_send_locked(prefix, body)
                if packet is not None or self._closing:
                    return packet
        else:
            async with self._lock:
                for _attempt in range(retries + 1):
                    packet = await self._async_send_locked(prefix, body)
                    if packet is not None or self._closing:
                        return packet
        _LOGGER.debug("No reply from %s for %s %s", self.host, prefix, body)
        return None

    async def _async_send_locked(self, prefix: str, body: str) -> ParsedPacket | None:
        if self._closing:
            return None
        if self._transport is None:
            try:
                await self._open_socket()
            except OSError as err:
                _LOGGER.debug("Could not open a UDP socket to %s: %s", self.host, err)
                return None
        quiet = prefix.startswith("0g")
        seq = self._seq
        self._seq = next_sequence(self._seq)
        future: asyncio.Future[ParsedPacket] = asyncio.get_running_loop().create_future()
        self._pending[seq] = future
        self._pending_noisy[seq] = not quiet
        frame = build_frame(prefix, seq, body)
        self._note(f"{_stamp()}  →  {self.host}  {_ascii_frame(frame)}", noisy=not quiet)
        assert self._transport is not None
        self._transport.sendto(frame)
        try:
            return await asyncio.wait_for(future, timeout=self.timeout)
        except TimeoutError:
            self._pending.pop(seq, None)
            self._pending_noisy.pop(seq, None)
            self._note(f"{_stamp()}  ×  {self.host}  timeout {prefix} {body}", noisy=True)
            return None
        except ConnectionError:
            _LOGGER.debug("UDP socket closed waiting for %s %s", prefix, body)
            return None


async def async_probe_firmware(host: str, port: int, timeout: float) -> str | None:
    """Return firmware string if the chassis answers GET c4.sy.fwv, else None."""
    identity = await async_probe_identity(host, port, timeout)
    return None if identity is None else identity.firmware


@dataclass
class ProbeIdentity:
    firmware: str | None
    info: str | None
    model_id: str | None
    # It answered c4.amp.ain, but not the way an amp does (for example the audio switch).
    not_amp: bool = False


async def async_probe_identity(host: str, port: int, timeout: float) -> ProbeIdentity | None:
    """GET firmware/info and pick the amp model from the ain reply."""
    from .discovery import model_from_probe
    from .protocol import parse_hex_list

    client = C4UdpClient(host, port, timeout)
    try:
        await client.async_start()
        fw = await client.async_send("0g", "c4.sy.fwv", retries=GET_RETRIES)
        if fw is None:
            return None
        firmware = fw.args[0].strip('"') if fw.args else ""
        info_pkt = await client.async_send("0g", "c4.sy.info", retries=GET_RETRIES)
        info = None
        if info_pkt and info_pkt.args:
            info = info_pkt.args[0].strip('"')
        amp = await client.async_send("0g", "c4.amp.ain", retries=GET_RETRIES)
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Identity probe failed for %s:%s", host, port)
        return None
    finally:
        await client.async_stop()

    model_id = None
    if amp is not None and amp.status_code not in REJECTED:
        values = [item for item in parse_hex_list(amp.args) if item is not None]
        model_id = model_from_probe(info, len(values))
    return ProbeIdentity(
        firmware=firmware,
        info=info,
        model_id=model_id,
        not_amp=amp is not None and model_id is None,
    )
