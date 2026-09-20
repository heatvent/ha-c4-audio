# Control4 Audio

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/heatvent/ha-c4-audio)
[![GitHub release](https://img.shields.io/github/v/release/heatvent/ha-c4-audio)](https://github.com/heatvent/ha-c4-audio/releases)
[![HA](https://img.shields.io/badge/Home%20Assistant-2024.12%2B-blue.svg)](https://www.home-assistant.io/)

**GitHub:** https://github.com/heatvent/ha-c4-audio

Custom HACS integration for Control4 Ethernet **amplifiers** and the **C4-16ZAMSV3-B** 16×16 audio switch.

Talks **UDP 8750** straight to each chassis. It does **not** talk to Director.

> **Important:** Do not dual-control the same rooms with this integration and the official Control4 / Composer path. Last UDP sender wins.

---

## Hardware

| Model | Zones / outputs | Inputs | UDP namespace |
|---|---|---|---|
| C4-AMP108-1B | 4 stereo speaker zones | 8 | `c4.amp` |
| C4-16AMP3-B | 8 stereo speaker zones | 8 | `c4.amp` |
| C4-16ZAMSV3-B | 16 line-level outputs | 16 | `c4.asw` |

Add **one integration entry per chassis**. A second 8-zone amp is a second amp entry — not a “16-zone amp” model.

### Typical whole-home music layout

1. Streamer (e.g. WiiM) analog out → amp input  
2. Name only the amp zones you use; leave unused jacks blank  
3. 16×16 switch is **optional** — only if several line-level sources share one amp input  
4. Leave old AVR feed outputs unnamed so they never become `media_player`s  

---

## Install (HACS)

1. **HACS → Integrations → ⋮ → Custom repositories**
2. URL: `https://github.com/heatvent/ha-c4-audio` · Category: **Integration**
3. Download **Control4 Audio**, then **restart** Home Assistant
4. **Settings → Devices & Services → Add Integration → Control4 Audio** (`c4_audio`)

HACS follows **GitHub Releases** (`v1.0.8`, …), not the tip of `main`.

### Manual install

Copy only `custom_components/c4_audio` into your HA `custom_components` folder. Do **not** drop the whole git repo there, and do **not** rename the folder (Home Assistant uses the folder name as the domain).

---

## Setup

1. Pick the chassis (discovery or IP) and hardware type  
2. **Inputs** — one name per jack; leave blank to skip  
3. **Amp outputs** — name + room (area); blank name = no entity  
4. **Switch outputs** — Output 1…16 names only (no room picker); stay in the switch area  
5. Defaults are fine for volume, polling, and timeouts — change later under **Configure**

Named zones/outputs are `media_player`s. Each also gets a **Source** dropdown on the device page.

If sources plug **straight into the amp**, skip the switch entry and the amp↔switch link. Selecting a source only sends `c4.amp.out` to that jack. Every zone on the same jack hears the same analog feed — that is the wiring, not a mix.

---

## Features

- Per-zone on/off, volume, mute, and source select over UDP  
- Turn-on volume (default **10%**) after route, while still muted  
- **All on** / **All off** buttons and an **All zones** switch per chassis  
- Services: `c4_audio.turn_on_all`, `turn_off_all`, `set_route`, `send_command`  
- Without `host`, All on/off target **amps only** (pass switch IP for named switch outputs)  
- Optional amp↔switch carry-through for shared buses  
- Diagnostic **UDP activity** sensor (SET / replies / `0t`, not GET polls)  
- Bass / treble number entities when EQ is enabled  

---

## Status polling

Each chassis is polled about every **15 seconds** (5–300 configurable): firmware, routes (`ain`), volume, mute, and bass/treble when EQ is on. After a SET, the chassis (and linked switch) are re-read immediately. Unsolicited `0t` frames are applied when the hardware sends them.

### UDP activity card example

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

### Whole-home helpers

Each chassis has **All on** / **All off** buttons and an **All zones** switch (on if any named zone is on). Expose **All zones** to Alexa, or call the buttons / `c4_audio.turn_on_all` / `turn_off_all`.

Example Music dashboard (WiiM + amp zones): [examples/ha-dashboard](examples/ha-dashboard).

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
