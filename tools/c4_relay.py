"""UDP relay between Control4 Director and an amp or 16x16 switch.

Same pattern as your old intermediary: Director is pointed at this PC's IP.
This process binds UDP 8750, forwards to the real device, and returns replies
to Director. Everything is logged so you can annotate what you tapped in Navigator.

Example:

    python tools/c4_relay.py --bind 192.168.2.185 --device 192.168.2.200 --controller 192.168.2.60 --log logs/switch.txt

While it runs, type a short note and press Enter after each Navigator action
(for example: "kitchen to input 3"). Notes are written into the log.
Ctrl+C stops.
"""

from __future__ import annotations

import argparse
import socket
import sys
import threading
from datetime import datetime
from pathlib import Path


def now() -> str:
    return datetime.now().isoformat(sep=" ", timespec="milliseconds")


def decode(data: bytes) -> str:
    return data.decode("utf-8", errors="replace").strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Control4 UDP 8750 intermediary logger")
    parser.add_argument("--bind", required=True, help="This PC's LAN IP (what Director will talk to)")
    parser.add_argument("--bind-port", type=int, default=8750)
    parser.add_argument("--device", required=True, help="Real amp or switch IP")
    parser.add_argument("--device-port", type=int, default=8750)
    parser.add_argument("--controller", default="", help="Director IP. If omitted, any non-device sender is treated as Director")
    parser.add_argument("--log", default="", help="Optional log file path")
    args = parser.parse_args()

    log_path = Path(args.log) if args.log else None
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.bind, args.bind_port))
    sock.settimeout(0.25)

    controller_dest: tuple[str, int] | None = None
    lock = threading.Lock()
    stop = threading.Event()

    def write(line: str) -> None:
        print(line, flush=True)
        if log_path:
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")

    def notes() -> None:
        write(f"{now()} - NOTE type a label after each Navigator action, then Enter")
        while not stop.is_set():
            try:
                line = input()
            except (EOFError, KeyboardInterrupt):
                stop.set()
                return
            if line.strip():
                write(f"{now()} - ACTION {line.strip()}")

    threading.Thread(target=notes, daemon=True).start()
    write(
        f"{now()} - LISTEN {args.bind}:{args.bind_port} -> {args.device}:{args.device_port}"
        + (f" controller={args.controller}" if args.controller else "")
    )

    try:
        while not stop.is_set():
            try:
                data, addr = sock.recvfrom(2048)
            except TimeoutError:
                continue
            except socket.timeout:
                continue
            src_ip, src_port = addr
            text = decode(data)

            if src_ip == args.device:
                dest = controller_dest
                if dest is None:
                    write(f"{now()} - ORPHAN from device {src_ip}:{src_port} : {text}")
                    continue
                sock.sendto(data, dest)
                write(f"{now()} - RESPONSE {dest[0]}:{dest[1]} <<< {args.device}:{args.device_port} : {text}")
                continue

            if args.controller and src_ip != args.controller:
                write(f"{now()} - UNKNOWN {src_ip}:{src_port} : {text}")
                continue

            with lock:
                controller_dest = (src_ip, src_port)
            sock.sendto(data, (args.device, args.device_port))
            write(
                f"{now()} - COMMAND {src_ip}:{src_port} >>> {args.device}:{args.device_port} : {text}"
            )
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        sock.close()
        write(f"{now()} - STOP")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
