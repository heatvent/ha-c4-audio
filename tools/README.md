# Test tools (UDP 8750)

Two small scripts, no Home Assistant required. Run them from this repo on a PC that can reach the amp or 16×16.

```powershell
cd C:\Users\Matt\ha-c4-audio
python tools\c4_probe.py --host 192.168.x.x
python tools\c4_relay.py --bind 192.168.x.x --device 192.168.x.x --controller 192.168.x.x --log logs\capture.txt
```

## 1. Probe — confirm the protocol without Director

The amp (and likely the switch) replies to **whoever sent the UDP packet**. You do not need the intermediary to test GETs and a careful SET.

```powershell
python tools\c4_probe.py --host AMP_OR_SWITCH_IP
```

That sends:

- `c4.sy.fwv`
- `c4.amp.psave`
- `c4.amp.ain` / `avol` / `amut` / `abss` / `atrb`

If you get `0r… 000` and a firmware string, the device speaks this language. If every command times out, the IP/port is wrong or the unit is not on the LAN. If you get `n01`, that GET exists on amps but not on that firmware.

Single commands:

```powershell
python tools\c4_probe.py --host 192.168.2.169 --get "c4.amp.ain"
python tools\c4_probe.py --host 192.168.2.169 --set "c4.amp.out 01 03"
python tools\c4_probe.py --host 192.168.2.169 --interactive
```

In interactive mode, type `c4.amp.out 02 01` or force get/set with `g:c4.amp.ain` / `s:c4.amp.mute 02 00`.

Do not run the probe against a zone someone is listening to unless you intend to change it. Identify (GET-only) is safe. `--set` will change routing/volume.

Do not run the probe and Director against the same device at the same time unless you are using the relay. Replies go to the last sender.

## 2. Relay — capture what Director actually sends (16×16)

This is the same idea as your old `UDP_intermediary.py`: Director talks to this PC, this PC talks to the real chassis, both directions are logged.

1. Pick a spare static IP on this PC (`--bind`), or use the PC's current LAN IP if nothing else is using **UDP 8750**.
2. In Composer, set the **16×16** (or amp) network identity / IP to that bind address so Director sends 8750 traffic here — same as you did for the AMP108.
3. `--device` is the **real** switch/amp IP.
4. `--controller` is Director's IP (optional but quieter logs).
5. Start the relay, then only do **one** Navigator action at a time. After each action, type a label and press Enter (`zone 1 to input 4`). That line is stored next to the packets.

```powershell
python tools\c4_relay.py --bind 192.168.2.185 --device 192.168.2.200 --controller 192.168.2.60 --log logs\zams-capture.txt
```

Useful first actions on the switch:

- Identify / refresh the device in Composer (firmware, subscribe)
- Route input 1 → output 1
- Route a different input to the same output
- Disconnect / turn that output off
- Volume or mute on one output, if Composer exposes it

A 16×16 is mostly **input → output**. Expect `c4.amp.out {output} {input}` (and maybe volume/tone). If the names differ (`c4.sw.*`, extra args), the log will show them.

Windows may prompt for firewall access the first time; allow UDP 8750.

## 3. What “good” looks like

Amp identify:

```text
SENT  '0g1001 c4.sy.fwv'
RECV  0r1001 000 c4.sy.fwv "03.24.45"
```

Switch: same shape, possibly more hex bytes on `ain` (up to 16). Timeout on every command means we never reached 8750. Mix of `000` and `n01` still means the framing is right.
