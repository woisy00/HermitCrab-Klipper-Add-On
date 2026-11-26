# Copilot instructions

## Project overview

This repository is a Klipper extension for managing manual tool changes on a
HermitCrab toolhead. The extension is intended to:

- Live in `extras/` and integrate with Klipper's extension-loading mechanism.
- Load toolhead definitions into the extension's runtime objects, merging their
  settings with the existing Klipper configuration rather than replacing
  unrelated configuration.
- Keep head-specific values such as PID settings, probe `z_offset`, and other
  calibration data with the currently active toolhead configuration.
- Provide `install.sh` to link extension modules into a Klipper installation
  and remove those links without changing unrelated files.

Treat toolhead configuration as belonging to its individual head. When the
active head changes, use that head's settings and calibration values; do not
silently apply one head's data to another.

The main `printer.cfg` owns shared hardware configuration and includes
`hc/hermitcrab.cfg` (copied from `macros/hermitcrab.cfg`), which holds the
`[hermitcrab]` section, the macros, and `[include toolheads.cfg]`. The toolhead file
(`hc/toolheads.cfg` by default) is included only by `hc/hermitcrab.cfg` and contains one
`[hc_head <name>]` section per toolhead, with that head's values only. The active head is stored in the toolhead file as `active_head` in a
`[hermitcrab state]` section. `SAVE_HEAD` writes calibration values back into the
matching `[hc_head <name>]` section.

## Repository conventions

- Keep Klipper-facing extension code in `extras/`. Keep installation-related
  Python code in `installer/` if it is added.
- Use `./install.sh install /path/to/klipper` and
  `./install.sh uninstall /path/to/klipper` to manage links in Klipper's
  `klippy/extras/` directory. The script must never replace existing files.
  Use `./install.sh config /path/to/printer_data/config` to copy the macros to
  `hc/` and add the includes to `printer.cfg`; it keeps existing files.
- The Klipper modules are `extras/hermitcrab.py` (`[hermitcrab]`: commands and
  status) and `extras/hc_head.py` (`[hc_head <name>]` sections). Keep their
  G-code commands, status object, and file writes consistent with `README.md`.
- Head changes apply live through `SET_HEAD`; do not restart Klipper for them.
- Write only the settings owned by this extension. `SAVE_HEAD` changes only the
  matching `[hc_head <name>]` section and keeps the commented option template.
- Retain compatibility with Python 3.8 and Klipper's runtime environment.
- Use four-space indentation, double-quoted strings, and an 88-character line
  length for Python, following the Ruff configuration in `pyproject.toml`.
- Keep function signatures and implementation bodies type-checkable under the
  strict mypy settings in `mypy.ini`.
- Add focused tests for behavior changes, especially configuration merging,
  active-head calibration selection, and installer link/unlink behavior.

## Validation

The project configures pytest to discover tests under `tests/`. For Python
changes, run the focused relevant tests, then the applicable checks:

```sh
pytest
ruff check extras installer
mypy
```

Do not assume a Klipper checkout is present in this repository; local Klipper
imports are optional, and the project configures type-checking stubs under
`klipper_stubs/`.
