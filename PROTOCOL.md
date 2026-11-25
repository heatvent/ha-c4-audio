# Control4 Ethernet audio protocol

There is **no public Control4 API document** for these chassis. What exists is a shared ASCII command language Control4 uses on many devices (amps, keypads, etc.), reverse-engineered from live traffic.

This file is the command/response set used by this integration, with what is confirmed vs guessed.

## Transport

| Item | Value |
|---|---|
| Port | **UDP 8750** |
| Encoding | ASCII |
| Terminator | `\r\n` |
| Discovery | SDDP (not required for control) |

Same port and framing appear on C4-AMP108, C4-8AMP1, and C4-16AMP3-class matrix amps. The Control4 audio switch (C4-16ZAMSV3-B / AVM-16S1-B) uses a different command set, `c4.asw`, and is not supported. It answers `c4.amp` with an empty `0r`. A **Triad** audio matrix is a different product (TCP + binary) and is **not** this protocol.

## Packet framing

Control4 uses a one-letter type + hex sequence, then a space, then the command.

```text
{type}{seq} {body}\r\n
```

| Type | Meaning | Example |
|---|---|---|
| `0s` | Set | `0se76c c4.amp.out 02 01` |
| `0g` | Get / query | `0g630b c4.sy.fwv` |
| `0r` | Reply to that sequence | `0re76c v01` or `0r630b 000 c4.sy.fwv "03.24.45"` |
| `0t` | Unsolicited status | `0t0040 sa c4.amp.mute 02 00` |

The same `0s` / `0g` / `0r` ASCII scheme shows up on other Control4 hardware (for example Zigbee keypads use `0s`/`0r` with `c4.kp.*`). That is independent confirmation that this is the company-wide command language, not an amp-only hack.

### Reply status tokens

| Token | Meaning (from captures + community) |
|---|---|
| `000` | OK; GET often echoes the command and values |
| `v01` | Seen on SET in the old capture; on a C4-8AMP1-B it means the value is out of range and nothing changed |
| `n01` | Not supported on this firmware/model |
| `e00` | Error (bad args — e.g. mute without `00`/`01`) |

Unsolicited `0t` frames include `sa` (“status available”) then the same `c4.amp.*` body the controller would have set.

## Volume scale

Hardware volume is one hex byte:

**percent + 155** → `00%` = `9b`, `12%` = `a7`

This matches:

- AMP108 captures (`chvol 02 a7` while lowering volume through `a2`, `a0`, `9f`)
- The current Control4 HA matrix-amp integration (`hex(percentage + 155)`)

Older community scripts used **+160**. That is about 5% hot and should not be used.

## Commands confirmed on C4-AMP108-1B

Source: live UDP log between Director (`192.168.2.60`) and amp (`192.168.2.169:8750`), plus the same names in public HA integrations.

### Zone routing and power

Director turns a room **on** in this order:

1. `0g … c4.amp.digi {input}` — query digital-input flag for that jack  
2. `0s … c4.amp.out {zone} {input}` — route  
3. `0s … c4.amp.mute {zone} 00` — unmute  
4. `0s … c4.amp.chvol {zone} {vol}` — set volume  

Director turns a room **off** as:

1. `c4.amp.mute {zone} 01`  
2. `c4.amp.out {zone} 00`  

`input` / `zone` are **1-based hex bytes** (`01` = jack 1). `00` on `out` disconnects the zone (treated as off).

AMP108 GET `c4.amp.ain` returned **four** hex bytes (four stereo zones). A C4-16AMP3-B should return **eight**.

### Volume, mute, limits

| Direction | Command | Notes |
|---|---|---|
| SET | `c4.amp.chvol {zone} {hex}` | Immediate volume |
| SET | `c4.amp.mute {zone} 00\|01` | `01` = muted. Mute **requires** the second byte (`e00` without it) |
| GET | `c4.amp.avol` | All zone volumes |
| GET | `c4.amp.amut` | All mute flags |
| GET | `c4.amp.vlim` | Volume limits (`00` = none) |
| Status | `c4.amp.chlim {zone} 00` | Unsolicited after volume ramps |

Do **not** send `c4.amp.chvolmax` from a volume slider. Public HA code documents a firmware bug: that command can jump the live volume to the cap.

### Tone / EQ / gain

| Direction | Command |
|---|---|
| SET | `c4.amp.bassgain {zone} {signed hex}` |
| SET | `c4.amp.trebgain {zone} {signed hex}` |
| SET | `c4.amp.bassfreq {zone} {hex}` |
| SET | `c4.amp.trebfreq {zone} {hex}` |
| SET | `c4.amp.eq {zone} {five 6-digit groups}` |
| SET | `c4.amp.igain {input} {hex}` (source leveling; `ff` ≈ −1 dB in the capture notes) |
| GET | `c4.amp.abss` / `atrb` / `abal` / `igain {n}` |
| Status | `c4.amp.tone {zone} {bass} {bassfreq} {treble} {trebfreq}` |

Signed gains are 8-bit two’s complement (`00` = 0 dB, `ff` = −1, `03` = +3). SET `c4.amp.bal` changes balance (confirmed on the 16AMP3, below; not captured on AMP108); GET is `c4.amp.abal`.

### Power save and system

| Direction | Command | Capture notes |
|---|---|---|
| GET | `c4.sy.fwv` | `"03.24.45"` on the logged AMP108 |
| GET | `c4.amp.psave` | Returned `01` |
| SET | `c4.amp.psave 00` | Wake |
| SET | `c4.amp.psave 02` | Status `psave 00 02` — power-save **disable** |
| SET | `c4.amp.psave 03` | Status `psave 00 03` — power-save **enable** |
| SET | `c4.sy.sub "ethernet"` | Subscribe Ethernet events |

Some HA scripts send **`c4.amp.psave 00 00`** (two bytes) to wake. Your AMP108 accepted the **one-byte** `00` form. This integration uses the captured one-byte wake.

GET `c4.sy.afwv` returned `n01` (not supported) on that amp.

## C4-8AMP1-B

From Control4's own driver descriptor (`amp3_4Ch_control4.c4i`): 4 zones, 4 inputs, UDP 8750, same control driver as the 16AMP3. Inputs 1 and 3 are analog **or** digital coax, not both.

Live-tested on firmware `03.24.45`, `c4.sy.info` = `v1_8chanamp:c4-8AMP1-B:<mac>`. The earlier "AMP108" capture has the same firmware, zone count, and Director address, so it was very likely this model.

| Command | Result |
|---|---|
| SET `c4.amp.psave 00` | `000`; GET `psave` reads `00` |
| SET `c4.amp.out {zone} 01`–`04` | `000`, reads back in `ain` |
| SET `c4.amp.out {zone} 05`–`09`, or zone 5 | `v01`, nothing changes |
| SET `c4.amp.mute`, `bassgain`, `trebgain` (±12) | `000`, reads back |
| SET `c4.amp.chvol` | `000`, reads back, except 0% (`9b`) which reads back as 1% (`9c`) |
| SET `c4.amp.bal` (±10) | `000`, reads back in `abal` |
| SET `c4.amp.igain` | Negative values read back. Positive values answer `000` but read back as `00` |
| GET `c4.amp.digi {input}` | `01` for inputs 1 and 3 (the digital jacks), `00` for the rest |

Both descriptors limit volume steps to one per 250 ms and list balance and input gain.

## C4-16AMP3-B

Checked on firmware `03.26.52`:

| Command | Reply |
|---|---|
| GET `c4.amp.abal` | 8 signed bytes, `00` = center |
| SET `c4.amp.bal {zone} {signed}` | `000`; `bal 08 01` reads back as `01` in `abal`, `00` restores it |
| GET `c4.amp.igain {input}` | input, then a signed byte, `00` = 0 dB |
| SET `c4.amp.igain {input} {signed}` | `000`; `igain 01 ff` reads back as `ff`, `00` restores it |
| GET `c4.amp.digi {input}` | `n01` (no digital inputs) — not sent on this model |
| GET `c4.sy.sub` | `"ethernet {Director ip:port}" "none"` — Director holds one slot. A second one may exist; this integration does not subscribe |


Same `c4.amp.*` names. GET lists return **eight** hex slots. `GET c4.amp.psave` is `n01` on firmware `03.26.52` — this integration does not send `psave` on that model.

## Independent public sources

- [HA: direct control of C4 amp (UDP 8750)](https://community.home-assistant.io/t/home-assistant-direct-control-of-control4-amp-and-tuner-no-plugin-needed/103497)
- [kmakar89/Home-Assistant---Control4](https://github.com/kmakar89/Home-Assistant---Control4) — reviewed below
- [OtisPresley/control4-mediaplayer](https://github.com/OtisPresley/control4-mediaplayer) — reviewed below
- Zigbee2MQTT C4 keypad discussion: same `0s`/`0r` + `c4.*.*` ASCII on a different product class

### kmakar89/Home-Assistant---Control4 (reviewed)

Hard-coded HA services for a **4-zone matrix amp** plus a **separate Control4 tuner** chassis. Not a HACS media-player integration.

What it actually sends (UDP 8750):

| Device | Command | Meaning |
|---|---|---|
| Amp | `c4.amp.out {zone} {input}` | Route. `00` = off |
| Amp | `c4.amp.chvol {zone} {hex}` | Volume |
| Amp | *(no mute, no GET/poll, no EQ)* | Optimistic UI only |
| Tuner | `c4.mt.tafreq2 00 {hex}` | Tuner 1 FM frequency |
| Tuner | `c4.mt.tbfreq2 00 {hex}` | Tuner 2 FM frequency |

FM encoding: station in MHz × 100, then hex (example `94.9` → `9490` → `2512`). That is a different product class from the amp; add it only if a C4 tuner is on the LAN.

Volume in that repo is **percent + 160**, then hex. Director captures and this integration use **percent + 155**. `+160` plays a few percent louder than Composer. Default power-on in their scripts is `chvol … a9`.

Framing is looser than Director (`0s2a` + two random digits, extra space before `\r\n`). The chassis still ACKs; sequence matching is not used.

Great Room is two amp zones (`03` and `04`) driven together — useful if a “room” is a pair of speaker outputs. Source names are mapped in automations (Tuner → jack 1, Volumio → 3, Bluetooth → 4), which is the same idea as this integration’s named inputs.

### OtisPresley/control4-mediaplayer (reviewed)

HACS **amp-only** media player (fork of Hansen8601). One HA config entry **per zone**, not per chassis. Volume formula matches this integration: **percent + 155**. Mute requires `00`/`01`. No GET polling — README claims the amp does not report state; that is **false** on 16AMP3 (`ain`, `avol`, `amut`, unsolicited `0t`).

Commands it sends:

| Command | Role | Notes vs this project |
|---|---|---|
| `c4.amp.out {zone} {input}` | Route; `00` = off | Same |
| `c4.amp.chvol {zone} {hex}` | Volume | Same scale (`9b` = 0%) |
| `c4.amp.mute {zone} 00\|01` | Mute | If reply contains `n01` or times out, they `chvol` to `9b` / restore |
| `c4.amp.bassgain` / `trebgain` | EQ sliders −12…+12 | Same two’s-complement hex |
| `c4.amp.bal {zone} {signed}` | Balance −10…+10 | SET name `bal` confirmed on 16AMP3; GET is `abal` |
| `c4.amp.psave 00 00` / `01 00` | Wake / power-save | **Two-byte** form. AMP108 accepted one-byte `psave 00`. 16AMP3 GET `psave` is `n01` |
| `c4.amp.chvolmax` | Hardware volume cap | **Firmware bug**: SET jumps live volume to the cap. They now keep the cap in software and only ever send `chvol`. Do not use from a slider |
| `c4.amp.chmode {zone} 00\|01\|02` | Output topology | `00` stereo, `01` mono summed, `02` bridged mono. In their manager, not exposed in the UI. Untested on 16AMP3 |
| `c4.amp.ingain {input} {hex}` | Input trim | They treat `80` as 0 dB, `7A`…`86` as −6…+6 dB. AMP108 captures used **`igain`**, not `ingain`. Do not send `ingain` until probed |

Framing is the kmakar style (`0s2a` + two random digits). They match replies by prefix (`0r2aXX`). Party mode is software: all zones `out` to the same input.

Useful product ideas (not new UDP): software max-volume cap, mute fallback, restore entity without blasting on HA reboot, optional `chmode` if we confirm it on the 16AMP3.
