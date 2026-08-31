# Changelog

This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html): **MAJOR.MINOR.PATCH** (for example `1.0.0`).

HACS shows the GitHub **release tag** (not a git commit hash). Each published version is a GitHub release named `v1.0.0`, `v1.0.1`, and so on.

## [1.0.0]

First SemVer release (replaces the short integer tags 1–7).

- Setup: IP and hardware, then name inputs, then name outputs
- Input/output screens say which jacks you are naming; empty boxes show Input 1 / Zone 1
- Each output is grouped as Zone 1, Zone 2, … with name and room
- Volume, polling, timeout, and switch link stay at defaults until Configure → Settings
- Amp turn-on volume defaults to 15%; max volume is Composer’s limit (`chvolmax` only when the zone is off)
- Switch line volume stays at 100%
- Discovery lists only Control4 amps and the 16×16 switch
- Switch hardware label is C4-16ZAMSV3-B

[1.0.0]: https://github.com/heatvent/ha-c4-audio/releases/tag/v1.0.0
