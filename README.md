# Aspiradora Xiaomi

[![Windows](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D4?logo=windows11&logoColor=white)](#requirements)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](#development)
[![Latest release](https://img.shields.io/github/v/release/Yakoderaa/Aspiradora-Xiaomi)](https://github.com/Yakoderaa/Aspiradora-Xiaomi/releases/latest)
[![Build](https://github.com/Yakoderaa/Aspiradora-Xiaomi/actions/workflows/build-release.yml/badge.svg)](https://github.com/Yakoderaa/Aspiradora-Xiaomi/actions/workflows/build-release.yml)

**A Windows desktop controller and live mapping project for the Xiaomi Robot Vacuum E10 (`xiaomi.vacuum.b112`).**

[Español](README.es.md) · [Português](README.pt-BR.md)

> This is an independent community project. It is not affiliated with or endorsed by Xiaomi.

## Why this project exists

Mi Home is the official experience, but a desktop workflow can be useful for people who want local controls, diagnostics, Windows integration, saved maps, scheduling, and a larger map viewport. This project focuses specifically on the Xiaomi Robot Vacuum E10/B112 and documents the reverse-engineering work required to understand its map and telemetry formats.

## Highlights

- Windows 10/11 desktop application with a native installer.
- Local E10 control over the same home network.
- Start cleaning, stop, return to dock, locate, suction and water controls.
- Persistent top-bar robot state: cleaning, returning, charging, idle and related states.
- Live map view with CAD-like zoom/pan behavior.
- Four local map slots, rooms, points, zones and virtual-wall tooling.
- Scheduler and Windows system-tray integration.
- Xiaomi account linking by QR plus local IP/token fallback.
- Automatic update checks with SHA-256 verification and an in-app GUI update flow.
- Light and dark themes.
- Spanish, English and Portuguese UI choices.
- F12 diagnostics for mapping, LAN/Cloud telemetry, docking, update state and decoder behavior.
- SteelSeries Sonar/Core Audio session naming support as **Aspiradora**.

## Mapping work

The E10/B112 does not expose its map in the same way as newer Xiaomi robot vacuums. The application therefore combines several signals:

- MIoT `10/24 robot-location` for live movement.
- Charging-base telemetry and physical dock status.
- Xiaomi Cloud map blobs.
- A decoded 120×120 2-bit grid candidate at 0.20 m resolution.
- Multi-frame accumulation and spatial validation before a native Xiaomi grid is allowed to replace the estimated view.

A key design rule is **do not invent room geometry**. Early, nearly linear movement is rendered only as a small observed footprint. Closed/flood-filled estimated rooms are delayed until there is genuine 2D exploration, while a validated Xiaomi grid always has priority.

More detail: [docs/MAPPING.md](docs/MAPPING.md).

## Installation

Download the latest installer from **Releases**:

**[Latest Windows release](https://github.com/Yakoderaa/Aspiradora-Xiaomi/releases/latest)**

The installer contains the desktop app, update helper and scheduler. Updating from inside the app verifies the downloaded installer with SHA-256 before installation.

## Requirements

- Windows 10 or Windows 11, x64.
- Xiaomi Robot Vacuum E10 / `xiaomi.vacuum.b112`.
- PC and robot connected to the same router for local control.
- Internet access is needed for Xiaomi Cloud/QR features and GitHub update checks.

## Privacy and security

- Local robot IP/token data is stored on the PC.
- Diagnostic screens intentionally redact signed FDS URLs and sensitive identifiers.
- Update installers are verified against a published SHA-256 file.
- The application does not intentionally expose Xiaomi credentials in F12 diagnostics.

See [SECURITY.md](SECURITY.md) for vulnerability reporting.

## Development

The project is written in Python and packaged with PyInstaller + Inno Setup.

```powershell
python -m pip install -r requirements.txt
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

The CI workflow compiles the application, runs the full smoke-test chain, validates packaged executables, builds the installer and publishes a tagged GitHub Release.

## Contributing

Bug reports are especially useful when they include:

1. App version.
2. What the robot physically did.
3. What Mi Home showed at the same time.
4. A screenshot of the desktop map.
5. The relevant F12 diagnostic block.

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Discoverability keywords

`xiaomi` · `xiaomi-vacuum` · `robot-vacuum` · `mi-home` · `smart-home` · `home-automation` · `windows` · `python` · `desktop-app` · `vacuum-map` · `b112` · `xiaomi-e10`
