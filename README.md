# Control4 Audio for Home Assistant

Custom HACS integration for Control4 Ethernet **amplifiers** and the **AVM-16S1-B / C4-16ZAMSV3-B** 16×16 audio switch.

It talks **UDP 8750** straight to each chassis. It does **not** talk to Director. If Composer / the Control4 app should stay in charge, do not enable this alongside the official Control4 integration for the same rooms.

## Hardware

| Model | Zones / outputs | Inputs | UDP namespace |
|---|---|---|---|
| C4-AMP108-1B | 4 stereo | 8 | `c4.amp` |
| C4-16AMP3-B | 8 stereo | 8 | `c4.amp` |
| 16-zone amplifier | 16 | 8 | `c4.amp` (second chassis or 16-slot firmware) |
| AVM-16S1-B / C4-16ZAMSV3-B | 16 line outputs | 16 | `c4.asw` |

Add **one integration entry per chassis**. Two 8-zone amps plus a switch is three entries.

## Install (HACS)

1. HACS → Integrations → Custom repositories → `https://github.com/heatvent/ha-c4-audio`, category **Integration**.
2. Download **Control4 Audio**, restart Home Assistant.
3. Settings → Devices & Services → Add Integration → **Control4 Audio**.

## Setup

1. Add the **switch** first (if you have one). Name outputs and inputs in jack order. Use `-` on a line to skip unused jacks.
2. Add each **amp**. Name rooms the same way.
3. On the amp, link the switch and set feeds. Default `1=1` means **amp input 1 is fed by switch output 1**. Extra buses are extra lines (`2=2`).
4. Amp room source lists then show **switch inputs** (WiiM, Retro Hi-Fi, …) plus any leftover local amp jacks.

Selecting **WiiM Pro** on Kitchen sends:

1. `c4.asw.out {switch output} {WiiM input}`
2. `c4.amp.out {kitchen zone} {amp input on that bus}`
3. unmute on both as needed

Every amp zone on the same bus hears the same matrix source. That is how the analog wiring works.

## Status polling

Each chassis is polled about every **15 seconds** (configurable 5–300): firmware, routes (`ain`), volume, mute, and bass/treble when EQ sliders are on. After a SET, the integration immediately re-reads that chassis (and the linked switch) so Home Assistant matches the hardware. Unsolicited `0t` status frames are applied when the amp/switch sends them.

## Controls (confirmed UDP)

**Amp (`c4.amp`)**

- Route / power: `out`, mute `00`/`01`
- Volume: `chvol` (percent + 155). Step ±1% in the UI. Do **not** send `chvolmax`.
- Tone: `bassgain` / `trebgain` as number entities
- Poll: `ain`, `avol`, `amut`, `abss`, `atrb`, `c4.sy.fwv`
- `psave` only on AMP108 (16AMP3 returns `n01`)

**Switch (`c4.asw`)**

- Route: `out` (output 16 is hex `10`)
- Mute; line volume `vol` (`64` = 100 = unity)
- Poll: `ain` (and volume/mute when the firmware answers)

**Services:** `c4_audio.send_command`, `c4_audio.set_route`, `c4_audio.turn_off_all`.

Protocol details: [PROTOCOL.md](PROTOCOL.md). Probe tools: [tools/README.md](tools/README.md).
