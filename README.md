# HermitCrab Klipper Add-On

This Klipper extension manages per-toolhead configuration profiles for manual
HermitCrab tool changes. Shared hardware settings stay in the main Klipper
configuration; each profile contains only values that differ for that head.

## Install

Link the extension into a Klipper checkout:

```sh
./install.sh install /path/to/klipper
```

In the directory containing `printer.cfg` (typically
`printer_data/config/`), create `toolheads/base.cfg` and
`toolheads/active.cfg` before the first Klipper restart. `base.cfg` may be
empty initially; `active.cfg` must exist as an empty file until a profile is
selected.

```sh
mkdir -p toolheads
touch toolheads/base.cfg
touch toolheads/active.cfg
```

Add the extension section and includes to `printer.cfg`. Keep shared hardware
settings before the toolhead layers; base values override shared settings, and
the selected profile overrides base values:

```ini
[hermitcrab]
toolheads_dir: toolheads

[include toolheads/base.cfg]
[include toolheads/active.cfg]
```

The default `toolheads_dir` is relative to the directory containing
`printer.cfg`. Profile names must start with a letter or digit and contain only
letters, digits, `_`, or `-`. The filenames `base.cfg` and `active.cfg` are
reserved and are not selectable profiles.

## Toolhead profiles

Create one Klipper configuration fragment per toolhead in
`printer_data/config/toolheads/`. Put common toolhead defaults in
`toolheads/base.cfg`. Keep shared hardware settings such as probe pins, sensor
types, and heater pins in `printer.cfg`; add only per-head overrides to each
profile:

```ini
# toolheads/tool0.cfg
[probe]
z_offset: 0.35

[extruder]
pid_Kp: 21.4
pid_Ki: 1.1
pid_Kd: 105.0
```

Klipper merges the shared `printer.cfg`, `base.cfg`, and selected profile in
that order; later values override earlier ones.
Profiles may also override values under `[safe_z_home]`,
`[screws_tilt_adjust]`, and `[z_tilt]`; use the complete, printer-specific
settings required by those Klipper modules.

`active.cfg` is a link to the selected profile. Its target persists across
Klipper restarts, so the last selected toolhead is loaded on startup.

## Select and store a toolhead

From the Mainsail/Fluidd G-code console, run:

```text
SET_ACTIVE_HEAD HEAD=tool0
```

Klipper switches `active.cfg` and restarts to load the selected profile. The
command refuses to run during an active virtual-SD print.

After `PROBE_CALIBRATE` or `PID_CALIBRATE`, use `STORE_ACTIVE_HEAD` instead of
`SAVE_CONFIG` to store the pending probe offset or PID values in the selected
profile:

```text
STORE_ACTIVE_HEAD
```

This writes a managed override block to the profile and restarts Klipper.
`STORE_ACTIVE_HEAD` currently stores pending probe `z_offset` and heater PID
values. It also updates the latest shared config file that defines the
corresponding section or property, following nested Klipper includes from
`printer.cfg`. Those shared values therefore become defaults for other heads
that do not override them. The selected profile retains its own copy. Edit
other per-head values, such as safe homing, screw positions, and Z-tilt
positions, directly in that head's profile.

Both commands refuse to run during an active virtual-SD print. Since applying a
profile restarts Klipper, only use them when it is safe to restart the printer.

Unlink the extension with:

```sh
./install.sh uninstall /path/to/klipper
```
