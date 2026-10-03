# Control4 Audio

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/heatvent/ha-c4-audio)
[![GitHub release](https://img.shields.io/github/v/release/heatvent/ha-c4-audio)](https://github.com/heatvent/ha-c4-audio/releases)
[![HA](https://img.shields.io/badge/Home%20Assistant-2024.12%2B-blue.svg)](https://www.home-assistant.io/)

**GitHub:** https://github.com/heatvent/ha-c4-audio

Custom HACS integration for Control4 Ethernet **amplifiers** and the **C4-16ZAMSV3-B** 16×16 audio switch.

Developed with [Cursor](https://cursor.com).

---

## How it works

Each chassis is a separate Home Assistant config entry. The integration opens a **UDP socket to port 8750** on that chassis and speaks Control4’s serial-over-UDP (`0s` / `0g` / `0r` / `0t`) under `c4.amp` (amps) or `c4.asw` (switch).

It does **not** talk to Director, Composer, or the Control4 cloud. HA is the controller for named zones.

> **Important:** Do not dual-control the same rooms with this integration and the official Control4 / Composer path. Last UDP sender wins.

### What a zone actually is

- **Amp:** a stereo speaker pair (physical output jack). Named jacks become `media_player`s; blank names are skipped.
- **Switch:** a line-level output. Named outputs become `media_player`s too, but they stay in the switch’s area (no room picker).
- **On** = routed to an input (`out` ≠ `00`). **Off** = muted and disconnected (`out 00`). There is no separate power rail command for zones.
- **Source select** writes `out` on that chassis. If the amp is linked to a matrix switch, picking a switch input also routes the switch’s feed output, then the amp input that carries that feed.

### Volume and turn-on

1. Route the zone while still muted  
2. Set volume with `chvol` (amps) or `vol` (switch)  
3. Unmute  

Default **turn-on volume is 10%** on amps (configurable). Switch line outputs default to **100%** (unity). A **max volume** setting is a software cap in HA only — the integration never sends `chvolmax` (16AMP3 firmware snaps live volume to that cap).

Off zones report the turn-on volume on the slider so Lovelace does not push 100% when you nudge volume. After a volume write, a stale high `avol` poll is ignored briefly so the UI does not jump.

**All on** only turns on zones that are off; rooms already playing keep their current volume. **All off** mutes and disconnects every named zone on that chassis.

### Amp ↔ switch carry-through (optional)

Use this when several line-level sources share one amp input through the 16×16 switch:

1. Add the switch as its own entry; name the inputs and only the outputs you care about  
2. On the amp entry → **Configure → Settings**, pick that switch and set feeds as `amp_input=switch_output` (default `1=1`)  
3. Amp zone source lists show **matrix inputs first**, then local amp jacks that are not fed by the switch  

Selecting a matrix source routes `switch_output ← switch_input`, then `amp_zone ← amp_input` for the feed. Zones on the same amp input share that analog bus — that is the wiring, not a software mix.

If sources plug **straight into the amp**, skip the switch entry and leave the link empty. Source select only sends `c4.amp.out`.

### Polling and activity

Each entry is polled about every **15 seconds** (5–300 configurable): firmware, routes (`ain`), volume, mute, and bass/treble when EQ is on. After any SET, that chassis (and a linked switch) are re-read immediately. Unsolicited `0t` frames update state when the hardware sends them.

A diagnostic **UDP activity** sensor logs SET commands, replies, and `0t` frames (not routine GET polls).

---

## Hardware

| Model | Zones / outputs | Inputs | UDP namespace |
|---|---|---|---|
| C4-AMP108-1B | 4 stereo speaker zones | 8 | `c4.amp` |
| C4-16AMP3-B | 8 stereo speaker zones | 8 | `c4.amp` |
| C4-16ZAMSV3-B | 16 line-level outputs | 16 | `c4.asw` |

Add **one integration entry per chassis**. A second 8-zone amp is a second amp entry — not a “16-zone amp” model.

Discovery lists Control4 amps and the 16×16 switch (DHCP / SDDP-style probes). You can always enter an IP manually.

### Typical whole-home music layout

1. Streamer (e.g. WiiM) analog out → amp input  
2. Name only the amp zones you use; leave unused jacks blank  
3. 16×16 switch is **optional** — only if several line-level sources share one amp input  
4. Leave old AVR feed outputs unnamed so they never become `media_player`s  

Amp zones are speakers (on/off, volume, source). Put play/pause / browse on the streamer or Music Assistant — not on the amp entities.

---

## Install (HACS)

1. **HACS → Integrations → ⋮ → Custom repositories**
2. URL: `https://github.com/heatvent/ha-c4-audio` · Category: **Integration**
3. Download **Control4 Audio**, then **restart** Home Assistant
4. **Settings → Devices & Services → Add Integration → Control4 Audio** (`c4_audio`)

HACS follows **GitHub Releases** (`v1.0.10`, …), not the tip of `main`.

### Manual install

Copy only `custom_components/c4_audio` into your HA `custom_components` folder. Do **not** drop the whole git repo there, and do **not** rename the folder (Home Assistant uses the folder name as the domain).

Brand icons for HA 2026.3+ live under `custom_components/c4_audio/brand/`.

---

## Setup

1. Pick the chassis (discovery or IP) and hardware type  
2. **Inputs** — one name per jack; leave blank to skip in source lists  
3. **Amp outputs** — name + room (area); blank name = no entity  
4. **Switch outputs** — Output 1…16 names only (no room picker); stay in the switch area  
5. Defaults are fine for volume, polling, and timeouts — change later under **Configure → Settings**

Named zones/outputs are `media_player`s. Each also gets a **Source** `select` entity on the device page.

---

## Entities per chassis

| Entity | Role |
|---|---|
| `media_player.*` | One per named amp zone or switch output |
| `select.*` | Source / input for that zone |
| `button.All on` / `button.All off` | Turn every named zone on or off |
| `switch.All zones` | On if any named zone is on; toggles All on / All off |
| `sensor.*_udp_activity` | Diagnostic SET / reply / `0t` log |
| `number` bass / treble | When EQ is enabled (amps only) |

Expose **All zones** to Alexa, or call the buttons / services from automations.

---

## Services

| Service | Behavior |
|---|---|
| `c4_audio.turn_on_all` | Turn on every enabled zone that is off (keeps volume on rooms already playing). Without `host`, **amps only**. |
| `c4_audio.turn_off_all` | Mute and disconnect every enabled zone. Without `host`, **amps only**. Pass the switch IP to include named switch outputs. |
| `c4_audio.set_route` | `output` + `input` (0 disconnects) on one chassis |
| `c4_audio.send_command` | Raw body, e.g. `c4.amp.out 01 03` |

Example Music dashboard (WiiM + amp zones): [examples/ha-dashboard](examples/ha-dashboard).

### UDP activity card

```yaml
type: markdown
title: Log
card_mod:
  style: |
    ha-card {
      max-height: 12em;
      overflow-y: auto;
    }
content: |
  {% set log = state_attr('sensor.media_closet_control4_amp_udp_activity', 'activity') %}
  ```
  {% if log %}{{ log.split('\n')[-20:] | join('\n') }}{% else %}idle{% endif %}
  ```
```

Use the entity ID from **Settings → Devices → your amp → UDP activity**.

---

## Controls (confirmed UDP)

### Amplifier (`c4.amp`)

| Function | Command / notes |
|---|---|
| Route / power | `out` · `00` = disconnected |
| Mute | `00` / `01` |
| Volume | `chvol` (percent + 155) · UI ±1% · software max cap |
| Tone | `bassgain` / `trebgain` number entities |
| Poll | `ain`, `avol`, `amut`, `abss`, `atrb`, `c4.sy.fwv` |

Do **not** send `chvolmax` on zone off — 16AMP3 firmware snaps live volume to the cap. `psave` works on AMP108; 16AMP3 returns `n01`.

### Switch (`c4.asw`)

| Function | Notes |
|---|---|
| Route | `out` (output 16 = hex `10`) |
| Mute / volume | Line `vol` (`64` = 100 = unity) |
| Poll | `ain` (and volume/mute when firmware answers) |

---

## Docs

| Doc | Contents |
|---|---|
| [CHANGELOG.md](CHANGELOG.md) | Release history (SemVer tags) |
| [PROTOCOL.md](PROTOCOL.md) | UDP framing and command notes |
| [tools/README.md](tools/README.md) | Probe / capture helpers |

---

## Related

For Music Assistant zone facades (decoder plays; amp zones are power/volume players), see [ha-amp-zone-player](https://github.com/heatvent/ha-amp-zone-player).
