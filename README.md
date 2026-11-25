# Control4 Audio

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/heatvent/ha-c4-audio)
[![GitHub release](https://img.shields.io/github/v/release/heatvent/ha-c4-audio)](https://github.com/heatvent/ha-c4-audio/releases)
[![HA](https://img.shields.io/badge/Home%20Assistant-2024.12%2B-blue.svg)](https://www.home-assistant.io/)

**GitHub:** https://github.com/heatvent/ha-c4-audio

Custom HACS integration for Control4 Ethernet **amplifiers**. The Control4 audio switch (C4-16ZAMSV3-B / AVM-16S1-B) is not supported.

Developed with [Cursor](https://cursor.com).

---

## How it works

Each chassis is a separate Home Assistant config entry. The integration opens a **UDP socket to port 8750** on that chassis and speaks Control4’s serial-over-UDP (`0s` / `0g` / `0r` / `0t`) under `c4.amp`.

It does **not** talk to Director, Composer, or the Control4 cloud. HA is the controller for named zones.

> **Important:** Do not dual-control the same rooms with this integration and the official Control4 / Composer path. Last UDP sender wins.

### What a zone actually is

- A **zone** is a stereo speaker pair (physical output jack). Named zones become `media_player`s; blank names are skipped.
- **On** = routed to an input (`out` ≠ `00`). **Off** = muted and disconnected (`out 00`). There is no separate power rail command for zones.
- **Source select** writes `out` on that chassis.

### Volume and turn-on

1. Route the zone while still muted  
2. Set volume with `chvol`  
3. Unmute  

Default **turn-on volume is 10%** (configurable). A **max volume** setting is a software cap in HA only — the integration never sends `chvolmax` (16AMP3 firmware snaps live volume to that cap).

Off zones show the turn-on volume. Volume up/down starts from that level and turns the zone on. Dragging the slider while the zone is off turns it on at the level you set. For a couple of seconds after a volume write, a stale poll or unsolicited volume frame is ignored. A command that gets no UDP reply leaves Home Assistant state unchanged.

**All on** wakes a 4-zone amp once, then turns on only the zones that are off. Rooms already playing keep their current volume. **All off** mutes and disconnects every named zone on that chassis.

### Polling and activity

Routes (`ain`), volume, and mute are polled about every **15 seconds** (5–300 configurable), and every **5 seconds** while a zone is on (2–300 configurable). Firmware and bass/treble keep the normal interval. Commands are sent one at a time. A read is tried three times and a command twice; the chassis is marked unavailable only after three polls in a row fail. After a turn on/off or source change, that chassis is re-read. Unsolicited `0t` frames update state when the hardware sends them, except a stale volume frame right after a write.

The integration does not subscribe to the amp's status events (`c4.sy.sub`), so it cannot take them away from Control4. Changes made by Control4 show up at the next poll.

### Changes made outside Home Assistant

When a zone changes and Home Assistant did not ask for it, the event `c4_audio_external_change` is fired. Data: `entity_id`, `zone`, `zone_name`, `changed` (`source`, `volume`, `muted`), `previous`, and the new `source`, `source_name`, `volume`, `muted`.

```yaml
triggers:
  - trigger: event
    event_type: c4_audio_external_change
    event_data:
      zone_name: Kitchen
```

### Experimental controls

**Configure → Settings → Show balance and input level** adds a balance slider per zone and a level slider per named input. Both are confirmed on the 16AMP3 for one step (balance +1, level -1 dB); the full range and the 4-zone amps are not tested, so each change is read back and an amp that ignores it reports an error.

A diagnostic **UDP activity** sensor logs SET commands, replies, and `0t` frames (not routine GET polls).

---

## Hardware

| Model | Zones | Inputs |
|---|---|---|
| C4-8AMP1-B (8 channels) | 4 stereo speaker zones | 4 (1 and 3 analog or digital) |
| C4-16AMP3-B (16 channels) | 8 stereo speaker zones | 8 |
| C4-AMP108-1B | 4 stereo speaker zones | 8 |

Add **one integration entry per chassis**. A second 8-zone amp is a second amp entry — not a “16-zone amp” model.

Discovery lists Control4 amps (DHCP / SDDP-style probes). You can always enter an IP manually.

### Typical whole-home music layout

1. Streamer (e.g. WiiM) analog out → amp input  
2. Name only the amp zones you use; leave unused jacks blank  
3. Leave old AVR feed outputs unnamed so they never become `media_player`s  

Amp zones are speakers (on/off, volume, source). Put play/pause / browse on the streamer or Music Assistant — not on the amp entities.

---

## Install (HACS)

1. **HACS → Integrations → ⋮ → Custom repositories**
2. URL: `https://github.com/heatvent/ha-c4-audio` · Category: **Integration**
3. Download **Control4 Audio**, then **restart** Home Assistant
4. **Settings → Devices & Services → Add Integration → Control4 Audio** (`c4_audio`)

HACS follows **GitHub Releases** (`v1.0.12`, …), not the tip of `main`.

### Manual install

Copy only `custom_components/c4_audio` into your HA `custom_components` folder. Do **not** drop the whole git repo there, and do **not** rename the folder (Home Assistant uses the folder name as the domain).

Brand icons for HA 2026.3+ live under `custom_components/c4_audio/brand/`.

---

## Setup

1. Pick the chassis (discovery or IP) and hardware type  
2. **Inputs** — one name per jack; leave blank to skip in source lists  
3. **Zones** — name + room (area) + optional turn-on volume; blank name = no entity  
4. Defaults are fine for volume, polling, and timeouts — change later under **Configure → Settings**

If the amp's address changes, use **Reconfigure** on the entry. Entities and settings are kept.

The room chosen during setup is applied only while the zone entity has no area. A room you set later in Home Assistant is kept.

Named zones are `media_player`s. Each also gets a **Source** `select` entity on the device page.

---

## Entities per chassis

| Entity | Role |
|---|---|
| `media_player.*` | One per named amp zone |
| `select.*` | Source / input for that zone |
| `button.All on` / `button.All off` | Turn every named zone on or off |
| `switch.All zones` | On if any named zone is on; toggles All on / All off |
| `sensor.*_udp_activity` | Diagnostic SET / reply / `0t` log |
| `number` bass / treble | When EQ is enabled |
| `number` balance / input level | When experimental controls are enabled |

Expose **All zones** to Alexa, or call the buttons / services from automations.

---

## Services

| Service | Behavior |
|---|---|
| `c4_audio.turn_on_all` | Turn on every enabled zone that is off (keeps volume on rooms already playing). Without a device, every amp. |
| `c4_audio.turn_off_all` | Mute and disconnect every enabled zone. Without a device, every amp. |
| `c4_audio.set_route` | `output` (zone) + `input` (0 disconnects) on one chassis. A device is required when more than one amp is installed. |
| `c4_audio.send_command` | Raw body, e.g. `c4.amp.out 01 03`. A device is required when more than one amp is installed. |

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

Do **not** send `chvolmax` on zone off — 16AMP3 firmware snaps live volume to the cap. AMP108 gets `psave 00` when a zone turns on, or once for All on (not on Home Assistant startup, and not once per zone). 16AMP3 returns `n01` for that command.

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
