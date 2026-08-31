import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "c4_audio"))

from protocol import (
    AmpCommands,
    DeviceCommands,
    build_frame,
    parse_packet,
    volume_hex_to_percent,
    volume_percent_to_hex,
)

assert volume_percent_to_hex(12) == "a7"
assert volume_hex_to_percent("a7") == 12
assert volume_percent_to_hex(0) == "9b"
prefix, body = AmpCommands.set_output(2, 1)
assert build_frame(prefix, 0xE76C, body) == b"0se76c c4.amp.out 02 01\r\n"
reply = parse_packet(b'0r630b 000 c4.sy.fwv "03.24.45"')
assert reply.kind == "reply"
assert reply.args[0] == '"03.24.45"'
status = parse_packet("0t0040 sa c4.amp.mute 02 00")
assert status.command == "c4.amp.mute"
sw = DeviceCommands("c4.asw", "vol", "percent_hex")
_prefix, route = sw.set_output(16, 4)
assert route == "c4.asw.out 10 04"
print("ok")
