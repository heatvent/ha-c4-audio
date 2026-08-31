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

Same port and framing appear on C4-AMP108, C4-8AMP1, C4-16AMP3-class matrix amps, and in community reports for the **C4-16ZAMSV3-B**. A **Triad** audio matrix is a different product (TCP + binary) and is **not** this protocol.

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
| `v01` | Accepted / “value ok” (common on SET volume/route) |
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

Signed gains are 8-bit two’s complement (`00` = 0 dB, `ff` = −1, `03` = +3). Community HA code uses SET `c4.amp.bal` for balance; AMP108 GET is `c4.amp.abal`. Treat balance SET as **not fully captured** on this chassis.

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

## C4-16AMP3-B

Same `c4.amp.*` names. GET lists return **eight** hex slots. `GET c4.amp.psave` is `n01` on firmware `03.26.52` — this integration does not send `psave` on that model.

## AVM-16S1-B / C4-16ZAMSV3-B (16×16 switch)

Live-tested on UDP **8750**. Namespace is **`c4.asw`**, not `c4.amp`.

| Direction | Command | Notes |
|---|---|---|
| GET | `c4.asw.ain` | 16 hex bytes, one per output |
| SET | `c4.asw.out {output} {input}` | Output **16** is hex `10`. `00` disconnects |
| SET | `c4.asw.mute {output} 00\|01` | |
| SET | `c4.asw.vol {output} {hex}` | **0–100 as hex**; `64` = 100 = unity. This is line trim, not a speaker amp |
| SET | `c4.asw.chvol …` | `n01` — not supported |

Do not use `c4.amp` / `c4.switch` / `c4.sw` on this chassis (empty `0r`).

A **Triad** 16×16 uses TCP binary and is not this integration.

## Independent public sources

- [HA: direct control of C4 amp (UDP 8750)](https://community.home-assistant.io/t/home-assistant-direct-control-of-control4-amp-and-tuner-no-plugin-needed/103497)
- [kmakar89/Home-Assistant---Control4](https://github.com/kmakar89/Home-Assistant---Control4) — reviewed below
- [OtisPresley/control4-mediaplayer](https://github.com/OtisPresley/control4-mediaplayer) — reviewed below
- Zigbee2MQTT C4 keypad discussion: same `0s`/`0r` + `c4.*.*` ASCII on a different product class

### kmakar89/Home-Assistant---Control4 (reviewed)

Hard-coded HA services for a **4-zone matrix amp** plus a **separate Control4 tuner** chassis. Not a HACS media-player integration, and it does **not** talk to an audio switch (`c4.asw` never appears).

What it actually sends (UDP 8750):

| Device | Command | Meaning |
|---|---|---|
| Amp | `c4.amp.out {zone} {input}` | Route. `00` = off |
| Amp | `c4.amp.chvol {zone} {hex}` | Volume |
| Amp | *(no mute, no GET/poll, no EQ)* | Optimistic UI only |
| Tuner | `c4.mt.tafreq2 00 {hex}` | Tuner 1 FM frequency |
| Tuner | `c4.mt.tbfreq2 00 {hex}` | Tuner 2 FM frequency |

FM encoding: station in MHz × 100, then hex (example `94.9` → `9490` → `2512`). That is a different product class from the amp/switch; add it only if a C4 tuner is on the LAN.

Volume in that repo is **percent + 160**, then hex. Director captures and this integration use **percent + 155**. `+160` plays a few percent louder than Composer. Default power-on in their scripts is `chvol … a9`.

Framing is looser than Director (`0s2a` + two random digits, extra space before `\r\n`). The chassis still ACKs; sequence matching is not used.

Great Room is two amp zones (`03` and `04`) driven together — useful if a “room” is a pair of speaker outputs. Source names are mapped in automations (Tuner → jack 1, Volumio → 3, Bluetooth → 4), which is the same idea as this integration’s named inputs.

### OtisPresley/control4-mediaplayer (reviewed)

HACS **amp-only** media player (fork of Hansen8601). One HA config entry **per zone**, not per chassis. Volume formula matches this integration: **percent + 155**. Mute requires `00`/`01`. No `c4.asw` / matrix switch. No GET polling — README claims the amp does not report state; that is **false** on 16AMP3 / AVM-16S1 (`ain`, `avol`, `amut`, unsolicited `0t`).

Commands it sends:

| Command | Role | Notes vs this project |
|---|---|---|
| `c4.amp.out {zone} {input}` | Route; `00` = off | Same |
| `c4.amp.chvol {zone} {hex}` | Volume | Same scale (`9b` = 0%) |
| `c4.amp.mute {zone} 00\|01` | Mute | If reply contains `n01` or times out, they `chvol` to `9b` / restore |
| `c4.amp.bassgain` / `trebgain` | EQ sliders −12…+12 | Same two’s-complement hex |
| `c4.amp.bal {zone} {signed}` | Balance −10…+10 | SET name `bal`; AMP108 GET is `abal`. Not live-tested here |
| `c4.amp.psave 00 00` / `01 00` | Wake / power-save | **Two-byte** form. AMP108 accepted one-byte `psave 00`. 16AMP3 GET `psave` is `n01` |
| `c4.amp.chvolmax` | Hardware volume cap | **Firmware bug**: SET jumps live volume to the cap. They now keep the cap in software and only ever send `chvol`. Do not use from a slider |
| `c4.amp.chmode {zone} 00\|01\|02` | Output topology | `00` stereo, `01` mono summed, `02` bridged mono. In their manager, not exposed in the UI. Untested on 16AMP3 |
| `c4.amp.ingain {input} {hex}` | Input trim | They treat `80` as 0 dB, `7A`…`86` as −6…+6 dB. AMP108 captures used **`igain`**, not `ingain`. Do not send `ingain` until probed |

Framing is the kmakar style (`0s2a` + two random digits). They match replies by prefix (`0r2aXX`). Party mode is software: all zones `out` to the same input.

Useful product ideas (not new UDP): software max-volume cap, mute fallback, restore entity without blasting on HA reboot, optional `chmode` if we confirm it on the 16AMP3.
