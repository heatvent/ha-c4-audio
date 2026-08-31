"""Async UDP client with sequence matching for Control4 audio devices."""

from __future__ import annotations

import asyncio
import logging
import socket
from collections.abc import Callable

from .protocol import ParsedPacket, build_frame, next_sequence, parse_packet

_LOGGER = logging.getLogger(__name__)


class C4UdpProtocol(asyncio.DatagramProtocol):
    def __init__(self, on_packet: Callable[[ParsedPacket], None]) -> None:
        self._on_packet = on_packet

    def datagram_received(self, data: bytes, addr) -> None:  # noqa: ANN001
        parsed = parse_packet(data)
        if parsed is None:
            return
        _LOGGER.debug("UDP from %s: %s", addr, parsed.raw)
        self._on_packet(parsed)


class C4UdpClient:
    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self._transport: asyncio.DatagramTransport | None = None
        self._seq = 0x1000
        self._pending: dict[int, asyncio.Future[ParsedPacket]] = {}
        self._listeners: list[Callable[[ParsedPacket], None]] = []
        self._lock = asyncio.Lock()

    def add_listener(self, callback: Callable[[ParsedPacket], None]) -> None:
        self._listeners.append(callback)

    async def async_start(self) -> None:
        loop = asyncio.get_running_loop()
        transport, _protocol = await loop.create_datagram_endpoint(
            lambda: C4UdpProtocol(self._handle_packet),
            remote_addr=(self.host, self.port),
            family=socket.AF_INET,
        )
        self._transport = transport

    async def async_stop(self) -> None:
        if self._transport is not None:
            self._transport.close()
            self._transport = None
        for future in self._pending.values():
            if not future.done():
                future.cancel()
        self._pending.clear()

    def _handle_packet(self, packet: ParsedPacket) -> None:
        if packet.kind == "reply" and packet.sequence in self._pending:
            future = self._pending.pop(packet.sequence)
            if not future.done():
                future.set_result(packet)
        for listener in self._listeners:
            try:
                listener(packet)
            except Exception:  # noqa: BLE001 — keep the socket loop alive
                _LOGGER.exception("Error in UDP listener")

    async def async_send(self, prefix: str, body: str) -> ParsedPacket | None:
        if self._transport is None:
            raise RuntimeError("UDP client is not started")

        async with self._lock:
            seq = self._seq
            self._seq = next_sequence(self._seq)
            loop = asyncio.get_running_loop()
            future: asyncio.Future[ParsedPacket] = loop.create_future()
            self._pending[seq] = future
            frame = build_frame(prefix, seq, body)
            _LOGGER.debug("UDP to %s:%s: %s", self.host, self.port, frame)
            self._transport.sendto(frame)

        try:
            return await asyncio.wait_for(future, timeout=self.timeout)
        except TimeoutError:
            self._pending.pop(seq, None)
            _LOGGER.warning("UDP timeout waiting for %s %s", prefix, body)
            return None


async def async_probe_firmware(host: str, port: int, timeout: float) -> str | None:
    """Return firmware string if the chassis answers GET c4.sy.fwv, else None."""
    client = C4UdpClient(host, port, timeout)
    try:
        await client.async_start()
        packet = await client.async_send("0g", "c4.sy.fwv")
    finally:
        await client.async_stop()
    if packet is None:
        return None
    if packet.args:
        return packet.args[0].strip('"')
    return ""
