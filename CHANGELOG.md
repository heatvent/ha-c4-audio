# Changelog

This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html): **MAJOR.MINOR.PATCH** (for example `1.0.0`).

HACS shows the GitHub **release tag** (not a git commit hash). Each published version is a GitHub release named `v1.0.0`, `v1.0.1`, and so on.

## [2.0.1]

Tested on a real C4-8AMP1-B (firmware 03.24.45): identification, wake, routing to all four inputs, mute, volume, bass, treble, balance, and input level.

- Adding an amp by hand works while Home Assistant shows a discovery card for it
- C4-8AMP1-B: the input level slider stops at 0 dB, because the amp ignores a higher level
- C4-8AMP1-B: a zone set to 0% no longer shows 1% (the amp stores 0% as 1%)

## [2.0.0]

### Breaking

- The Control4 audio switch (C4-16ZAMSV3-B / AVM-16S1-B, `c4.asw`) is no longer supported. The integration controls amps only. An existing switch entry stops loading with a message asking you to delete it; amp entries, entity IDs, and unique IDs are unchanged
- Amp entries lose the old *Matrix switch* / *Amp input = switch output* settings automatically. An amp that was linked to a switch now lists only its own named inputs
- Discovery skips the switch, and setup rejects a device that does not answer as an amp
- The unused 16-zone profile is removed. No Control4 amp with 16 zones is known; the 16 in C4-16AMP3-B is channels (8 stereo zones)
- A command the amp rejects (`n01` / `e00`) is now an error instead of being shown as done

### Added

- C4-8AMP1-B (8 channels, 4 zones, 4 inputs)
- `c4_audio_external_change` event when a zone changes and Home Assistant did not ask for it
- Zones turn on with their last source (option), and each zone can have its own turn-on volume
- Balance and input level controls (option, off by default, experimental). Each change is read back
- **Reconfigure** for a new IP address or port, and a confirm step with a readable name for discovered amps
- Services accept a device. `host` still works

### Changed

- The amp is polled every 5 seconds while a zone is on (option). Firmware and bass/treble keep the normal interval
- Volume is sent at most once per 250 ms per zone, always ending on the latest value
- Source, bass, and treble are configuration entities in their zone's room. A room you set yourself is kept
- The UDP activity log attribute is no longer recorded
- The C4-16AMP3-B no longer gets `c4.amp.digi`, which it rejects. On 4-zone amps a missing answer to it is ignored

### Fixed

- One lost UDP reply no longer makes every zone unavailable. Reads are tried three times, and three polls in a row must fail
- Commands are tried twice. A repeat never lands after a newer command
- All on / All off continue past a zone that fails, and to the next amp
- A zone routed to an unnamed input shows that input instead of Off
- A network error at startup is retried instead of failing for good
- Clearing a zone or input name in Configure works, and a cleared zone's entities are removed
- Choosing a source on a 4-zone amp that is off wakes it first
- Diagnostics work while the amp is not loaded, and hide the MAC address and IP

## [1.0.13]

- Keep the regular poll on schedule. Status frames from the chassis no longer postpone it, so firmware, bass/treble and availability stay current even while a keypad or volume ramp is sending updates
- Close the UDP socket only after every entity unloaded cleanly
- Pass the config entry to the coordinator explicitly (required by newer Home Assistant)
- Services are available as soon as Home Assistant starts, so automations validate before the chassis is reachable
- CI runs the test suite, with new setup/unload and polling tests

## [1.0.12]

- Send one UDP command at a time, and reopen the socket if it dies
- Do not update Home Assistant state when a command gets no reply
- Volume up/down and the slider turn an off zone on from the turn-on volume, or from the level you set
- Ignore a stale volume status frame for a few seconds after a write
- Mark the chassis unavailable when route, volume, or mute polls time out
- `set_route` and `send_command` require `host` when more than one chassis is configured, and reject jacks that chassis does not have
- Keep areas you set in Home Assistant; apply the setup room only when a zone has none
- Wake AMP108 power-save once per All on, and re-read the linked switch only after a matrix route

## [1.0.11]

- Entity unique IDs follow the chassis identity (not the IP), and existing entities are migrated so a DHCP change keeps names, areas, and history
- AMP108 power-save wake (`psave 00`) is sent only when a zone turns on, not on every Home Assistant start

## [1.0.10]

- Ship brand icons under `custom_components/c4_audio/brand/` (HA 2026.3+ local brands path)

## [1.0.9]

- Fix hassfest validation: empty labels for input/zone name fields (NBSP was rejected as trailing whitespace)
- Sort manifest.json keys for hassfest

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

[1.0.12]: https://github.com/heatvent/ha-c4-audio/compare/v1.0.11...v1.0.12
[1.0.11]: https://github.com/heatvent/ha-c4-audio/compare/v1.0.10...v1.0.11
[1.0.10]: https://github.com/heatvent/ha-c4-audio/compare/v1.0.9...v1.0.10
[1.0.9]: https://github.com/heatvent/ha-c4-audio/compare/v1.0.8...v1.0.9
[1.0.8]: https://github.com/heatvent/ha-c4-audio/compare/v1.0.7...v1.0.8
[1.0.7]: https://github.com/heatvent/ha-c4-audio/compare/v1.0.6...v1.0.7
[1.0.6]: https://github.com/heatvent/ha-c4-audio/compare/v1.0.5...v1.0.6
[1.0.5]: https://github.com/heatvent/ha-c4-audio/compare/v1.0.4...v1.0.5
[1.0.4]: https://github.com/heatvent/ha-c4-audio/compare/v1.0.2...v1.0.4
[1.0.3]: https://github.com/heatvent/ha-c4-audio/compare/v1.0.2...v1.0.3
[1.0.2]: https://github.com/heatvent/ha-c4-audio/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/heatvent/ha-c4-audio/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/heatvent/ha-c4-audio/releases/tag/v1.0.0
