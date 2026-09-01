# Control4 Audio for Home Assistant

Custom HACS integration for Control4 Ethernet **amplifiers** and the **C4-16ZAMSV3-B** 16×16 audio switch.

It talks **UDP 8750** straight to each chassis. It does **not** talk to Director. If Composer / the Control4 app should stay in charge, do not enable this alongside the official Control4 integration for the same rooms.

## Hardware

| Model | Zones / outputs | Inputs | UDP namespace |
|---|---|---|---|
| C4-AMP108-1B | 4 stereo speaker zones | 8 | `c4.amp` |
| C4-16AMP3-B | 8 stereo speaker zones | 8 | `c4.amp` |
| C4-16ZAMSV3-B | 16 line-level outputs | 16 | `c4.asw` (matrix switch, not a speaker amp) |

Add **one integration entry per chassis**. A second 8-zone amp is a second amp entry, not a “16-zone amp” model.

**Whole-home music (no AVRs on this path):** add the **C4-16AMP3-B** and put sources on its analog inputs (WiiM analog out is enough). Leave unused amp zones unnamed. The 16×16 switch is optional — only add it if several line-level sources still share one amp input. Leave switch outputs that used to feed receivers unnamed so they never become `media_player`s. Living room / basement ceilings stay off this integration unless you land those speakers on spare amp zones (the 16AMP3 has eight).

## Install (HACS)

1. HACS → Integrations → Custom repositories → `https://github.com/heatvent/ha-c4-audio`, category **Integration**.
2. Download **Control4 Audio**, restart Home Assistant.
3. Settings → Devices & Services → Add Integration → **Control4 Audio** (domain `c4_audio`).

Do not copy this whole git repo into `custom_components`, and do not rename the folder to `control4_amp`. Home Assistant loads the folder name as the domain; a `control4_amp` folder without `async_setup_entry` produces *No setup or config entry setup function defined*.

Releases and version history: [CHANGELOG.md](CHANGELOG.md).

## Setup

1. Add Integration → **Control4 Audio**. Pick the chassis (or enter IP) and the hardware type.
2. **Inputs:** one name box per jack. Leave a box empty to skip that input.
3. **Amp outputs:** one name box and a room dropdown per zone. Leave a name empty to skip that zone.
4. **Switch outputs:** name boxes labeled as Output 1, Output 2, … with no room picker. Named outputs stay in the same area as the switch.
5. Volume, polling, UDP timeout, bass/treble, and amp↔switch link stay at defaults. Change them later under **Configure** if needed.

Named outputs and zones are `media_player`s. Each also gets a **Source** dropdown on the same Home Assistant device so you can pick an input from the device page without opening more-info. Name the inputs in setup or those lists stay empty.

If WiiM (and anything else) are wired **straight into the amp**, skip the switch entry and the link. Selecting WiiM only sends `c4.amp.out` to that amp input. Every zone you route to the same amp jack hears the same analog source — that is the wiring, not a software mix.

## Status polling

Each chassis is polled about every **15 seconds** (configurable 5–300): firmware, routes (`ain`), volume, mute, and bass/treble when EQ sliders are on. After a SET, the integration immediately re-reads that chassis (and the linked switch) so Home Assistant matches the hardware. Unsolicited `0t` status frames are applied when the amp/switch sends them.

## Controls (confirmed UDP)

**Amp (`c4.amp`)**

- Route / power: `out`, mute `00`/`01`
- Volume: `chvol` (percent + 155). Step ±1% in the UI. Max volume is a software cap on the slider. Do **not** send `chvolmax` (firmware snaps live level to the cap).
- Tone: `bassgain` / `trebgain` as number entities
- Poll: `ain`, `avol`, `amut`, `abss`, `atrb`, `c4.sy.fwv`
- `psave` only on AMP108 (16AMP3 returns `n01`)

**Switch (`c4.asw`)**

- Route: `out` (output 16 is hex `10`)
- Mute; line volume `vol` (`64` = 100 = unity)
- Poll: `ain` (and volume/mute when the firmware answers)

**Services:** `c4_audio.send_command`, `c4_audio.set_route`, `c4_audio.turn_off_all`.

Example Home Assistant Music dashboard (WiiM + amp zones): [examples/ha-dashboard](examples/ha-dashboard).

Protocol details: [PROTOCOL.md](PROTOCOL.md). Probe tools: [tools/README.md](tools/README.md).
