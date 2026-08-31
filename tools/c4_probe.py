"""Send Control4 UDP commands and print replies.

Examples:

    python tools/c4_probe.py --host 192.168.2.169
    python tools/c4_probe.py --host 192.168.2.200 --identify
    python tools/c4_probe.py --host 192.168.2.169 --get "c4.amp.ain"
    python tools/c4_probe.py --host 192.168.2.169 --set "c4.amp.out 01 03"
    python tools/c4_probe.py --host 192.168.2.169 --interactive
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _c4udp import is_get_body, send_and_collect  # noqa: E402

IDENTIFY = [
    ("0g", "c4.sy.fwv"),
    ("0g", "c4.amp.psave"),
    ("0g", "c4.amp.ain"),
    ("0g", "c4.amp.avol"),
    ("0g", "c4.amp.amut"),
    ("0g", "c4.amp.abss"),
    ("0g", "c4.amp.atrb"),
]


def run_one(host: str, port: int, prefix: str, seq: int, body: str, timeout: float) -> int:
    packets, frame = send_and_collect(host, port, prefix, seq, body, timeout)
    print(f"SENT  {frame.decode('ascii').rstrip()!r}")
    if not packets:
        print("RECV  (timeout — no UDP reply)")
        return seq
    for packet in packets:
        print(f"RECV  {packet.raw}")
    return seq


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe a Control4 amp or matrix switch on UDP 8750")
    parser.add_argument("--host", required=True, help="Device IP")
    parser.add_argument("--port", type=int, default=8750)
    parser.add_argument("--timeout", type=float, default=1.5)
    parser.add_argument("--identify", action="store_true", help="Run GET suite (default if no --get/--set/--interactive)")
    parser.add_argument("--get", metavar="BODY", help='Query, e.g. "c4.amp.ain"')
    parser.add_argument("--set", metavar="BODY", help='Set, e.g. "c4.amp.out 01 03"')
    parser.add_argument("--cmd", metavar="BODY", help="Auto-choose 0g vs 0s from the command name")
    parser.add_argument("--interactive", action="store_true")
    args = parser.parse_args()

    seq = 0x1000
    did_work = args.get or args.set or args.cmd or args.interactive or args.identify

    if args.get:
        seq += 1
        run_one(args.host, args.port, "0g", seq, args.get, args.timeout)
    if args.set:
        seq += 1
        run_one(args.host, args.port, "0s", seq, args.set, args.timeout)
    if args.cmd:
        seq += 1
        prefix = "0g" if is_get_body(args.cmd) else "0s"
        run_one(args.host, args.port, prefix, seq, args.cmd, args.timeout)

    if args.interactive:
        print("Type a command body (c4.amp.out 01 02). Prefix with g: or s: to force get/set.")
        print("quit to exit.")
        while True:
            try:
                line = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return 0
            if not line or line in {"quit", "exit"}:
                return 0
            prefix = "0s"
            body = line
            if line.lower().startswith("g:"):
                prefix, body = "0g", line[2:].strip()
            elif line.lower().startswith("s:"):
                prefix, body = "0s", line[2:].strip()
            elif is_get_body(line):
                prefix = "0g"
            seq += 1
            run_one(args.host, args.port, prefix, seq, body, args.timeout)

    if not did_work or args.identify:
        print(f"Identify {args.host}:{args.port}")
        for prefix, body in IDENTIFY:
            seq += 1
            run_one(args.host, args.port, prefix, seq, body, args.timeout)
            print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
