# HermitCrab Klipper Add-On

This Klipper extension manages manual HermitCrab tool changes. Each toolhead is
one `[hc_head <name>]` section in a toolhead config file. Shared hardware
settings stay in `printer.cfg`.

## Install

Link the extension into a Klipper checkout:

```sh
./install.sh install /path/to/klipper
```

Copy the macros and the toolhead file into the printer's `config/hc/` folder and
add the include to `printer.cfg`:

```sh
./install.sh config /path/to/printer_data/config
```

This creates `hc/`, copies `macros/hermitcrab.cfg` to `hc/hermitcrab.cfg`, and
creates an empty `hc/toolheads.cfg`. Existing files are kept. It adds these
lines if they are missing: `[include hc/hermitcrab.cfg]` to `printer.cfg`
(before the `SAVE_CONFIG` block), and `[include toolheads.cfg]` to
`hc/hermitcrab.cfg`:

```ini
[include hc/hermitcrab.cfg]
```

`hc/hermitcrab.cfg` contains the `[hermitcrab]` section, the macros, and the
`[include toolheads.cfg]` line. Set `default_head` there to the head used when
nothing is stored yet. The toolhead file holds the `[hc_head <name>]` sections.
Do not also include it from `printer.cfg`, since Klipper rejects duplicate
sections. `[hermitcrab] file:` tells the manager where to write. Both paths are
relative to the directory containing the file that declares them.

The active head is stored in the toolhead file as `active_head` in a
`[hermitcrab state]` section. You don't need `[save_variables]`.

## Configuration

### `[hermitcrab]`

| Option         | Default       | Description                                          |
|----------------|---------------|------------------------------------------------------|
| `file`         | `toolheads.cfg` | Toolhead config file (relative to `printer.cfg`); the installer sets `hc/toolheads.cfg` |
| `default_head` | first head    | Head used when `active_head` is unset or unknown     |
| `heater`       | `extruder`    | Heater that receives the PID values                  |
| `extruder`     | `extruder`    | Extruder for pressure advance and rotation distance  |
| `pin_prefix`   | `TOOLHEAD_`   | `[output_pin <prefix><NAME>]` shows the active head  |

### `[hc_head <name>]`

Names may contain lowercase letters, digits and `_`. Every option is optional.
Unset options are not applied.

```ini
[hc_head emil]
x_offset: -35
y_offset: 0
z_offset: 0.455
pid_kp: 41.346
pid_ki: 10.602
pid_kd: 40.313
pressure_advance: 0.04
pa_smooth_time: 0.040
rotation_distance: 22.6789
probe_deploy_angle: 110
probe_stow_angle: 40
```

| Option                                | Applied by `SET_HEAD`                           |
|---------------------------------------|-------------------------------------------------|
| `x_offset`, `y_offset`, `z_offset`    | Probe offsets                                   |
| `pid_kp`, `pid_ki`, `pid_kd`          | Heater PID at runtime (same units as `PID_CALIBRATE`), only if all three are set and `pid_kp` > 0 |
| `pressure_advance`, `pa_smooth_time`  | `SET_PRESSURE_ADVANCE`                          |
| `rotation_distance`                   | `SET_EXTRUDER_ROTATION_DISTANCE`                |
| `probe_deploy_angle`, `probe_stow_angle` | Stored for macros only                       |

`logo` shows ASCII art above the values in `SET_HEAD` and `HEAD_INFO`. It is not
saved by `SAVE_HEAD`. Use `crab`, `cat`, or `custom`. With `custom`, set
`logo_custom` to the art on one line, with `|` between lines, for example
`logo_custom: /\_/\|( o.o )|> ^ <`. Leading spaces on the first line are dropped, and
a ` #` or ` ;` starts a comment, so avoid those in the art.

`ADD_HEAD` writes each new section with every option listed as a commented
placeholder, so the full list of settings is visible in the file. It also appends
`[output_pin TOOLHEAD_<NAME>]` on `virtual_pin:head_<name>` and a
`[gcode_macro USE_HEAD_<NAME>]` that runs `HC_SET_HEAD`, so the new head shows up
in the UI and in the active-head pin without manual edits. It refuses to write if
any of these sections already exists in `hc/toolheads.cfg`.

## Commands

Each command is a `[gcode_macro]` in `macros/hermitcrab.cfg`, so it shows up in the
UI. The macros forward to the Python commands `HC_<NAME>`.

| Command                         | Purpose                                                     |
|---------------------------------|-------------------------------------------------------------|
| `ADD_HEAD NAME=<name>`          | Add `[hc_head]`, `[output_pin TOOLHEAD_<NAME>]` and `USE_HEAD_<NAME>` |
| `SET_HEAD [HEAD=<name>]`        | Apply a head; defaults to the active head                   |
| `SAVE_HEAD [HEAD=<name>] [KEY=value ...]` | Store values in the head's section                |
| `HEAD_INFO [HEAD=<name>]`       | Show the stored values of a head                            |
| `SET_PROBE_OFFSET [X=] [Y=] [Z=]` | Set probe offsets at runtime (run `G28 Z` after changing Z) |

`SAVE_HEAD` without a `HEAD=` stores values for the active head: the live probe
offsets and the pending `z_offset` and PID values from `SAVE_CONFIG`. Explicit
`KEY=value` parameters, such as `PID_KP=41.3` or `Z_OFFSET=0.1`, override them.
Only changed values are written, and only to that head's section. No Klipper
restart is needed.

The `ADD_HEAD` example:

```text
ADD_HEAD NAME=willi
SET_HEAD HEAD=willi
SAVE_HEAD HEAD=willi Z_OFFSET=0.005
```

A new head is registered immediately and is written to `hc/toolheads.cfg`. It is
loaded on the next restart because the file is included by `hc/hermitcrab.cfg`.

## Status

The `hermitcrab` status object exposes `active`, `heads`, and `values` for the
active head, for example `printer.hermitcrab.active` in macros.

## Uninstall

```sh
./install.sh uninstall /path/to/klipper
```
