# Changelog

This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html): **MAJOR.MINOR.PATCH** (for example `1.0.0`).

HACS shows the GitHub **release tag** (not a git commit hash). Each published version is a GitHub release named `v1.0.0`, `v1.0.1`, and so on.

## [1.0.8]

- Volume-up from 0% no longer jumps to 100% (slider 0–1 vs 1% step)
- Selecting a source on an off zone uses the 10% turn-on volume before unmute
- All on leaves rooms that are already playing at their current volume
- Ignore a stale 100% volume poll for a couple of seconds after we write `chvol`
- Off zones report turn-on volume on the slider so Lovelace does not send 100%
- `turn_on_all` / `turn_off_all` without `host` only target amps, not the matrix switch
- Raw UDP helper no longer wraps GET frames as SET
- UDP activity lines are debug-level; area IDs are only written when they change

## [1.0.7]

- Each amp and switch has **All on** / **All off** buttons and an **All zones** switch (on if any named zone is on). Use those in automations or expose the switch to Alexa. Services `c4_audio.turn_on_all` and `c4_audio.turn_off_all` do the same.

## [1.0.6]

- Amp and switch devices expose a **UDP activity** sensor (SET commands, replies, and unsolicited `0t` frames). Polling GETs stay in debug logs. Put it on a dashboard with a markdown card on `state_attr('sensor.…_udp_activity', 'activity')`.

## [1.0.5]

- Amp zones turn on at 10% (not the leftover 100% from `chvolmax`). Change it under Configure → Settings → Turn-on volume.
- Set volume after the zone is routed and still muted; 16AMP3 ignores `chvol` while disconnected.

## [1.0.4]

- Do not send `chvolmax` when a zone turns off (16AMP3 firmware jumps live volume to 100%)
- Set zone volume before unmute so turning a room on is not a brief full-blast
- Input and output name boxes use a gray in-field hint (Input 1, Zone 1, Output 1) instead of a prefix label
- Switch outputs are labeled Output 1…16 with no room/area picker; they stay in the switch’s area
- Each named amp zone and switch output has a Source/Input dropdown on the device page (and as a `select` entity)

## [1.0.3]

- Turning a zone on uses the first named input if none is already routed

## [1.0.2]

- Input/output boxes use a single gray prefix (`Input 1 Name`, `Zone 1 Name`) without a second white label
- Output name and room are sequential fields (Home Assistant cannot place them on one row)

## [1.0.1]

- Fix setup crash (`Unknown error occurred`) after entering the amp IP: Home Assistant text fields do not support `placeholder`

## [1.0.0]

First SemVer release (replaces the short integer tags 1–7).

- Setup: IP and hardware, then name inputs, then name outputs
- Input/output screens say which jacks you are naming; empty boxes show Input 1 / Zone 1
- Each output is grouped as Zone 1, Zone 2, … with name and room
- Volume, polling, timeout, and switch link stay at defaults until Configure → Settings
- Amp turn-on volume defaults to 15%; max volume is a software cap (do not send `chvolmax`)
- Switch line volume stays at 100%
- Discovery lists only Control4 amps and the 16×16 switch
- Switch hardware label is C4-16ZAMSV3-B

[1.0.8]: https://github.com/heatvent/ha-c4-audio/compare/v1.0.7...v1.0.8
[1.0.7]: https://github.com/heatvent/ha-c4-audio/compare/v1.0.6...v1.0.7
[1.0.6]: https://github.com/heatvent/ha-c4-audio/compare/v1.0.5...v1.0.6
[1.0.5]: https://github.com/heatvent/ha-c4-audio/compare/v1.0.4...v1.0.5
[1.0.4]: https://github.com/heatvent/ha-c4-audio/compare/v1.0.2...v1.0.4
[1.0.3]: https://github.com/heatvent/ha-c4-audio/compare/v1.0.2...v1.0.3
[1.0.2]: https://github.com/heatvent/ha-c4-audio/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/heatvent/ha-c4-audio/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/heatvent/ha-c4-audio/releases/tag/v1.0.0
