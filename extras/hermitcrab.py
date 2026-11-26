# HermitCrab toolhead manager for the [hermitcrab] section.
#
# Each toolhead is a [hc_head <name>] section in the toolhead config file and
# is loaded as an HCHead object (see hc_head.py). The active head is stored in
# the [hermitcrab state] section of the same file as active_head.
#
# Commands (registered as HC_<name>, wrapped by [gcode_macro <name>] in
# macros/toolhead.cfg so they show up in the UI):
#   SET_HEAD [HEAD=<name>]        apply a head (default: active head)
#   SAVE_HEAD [HEAD=<name>] [KEY=value ...]
#                                 write current/pending values into the head's
#                                 section (no restart needed)
#   ADD_HEAD NAME=<name>          add an empty, commented [hc_head <name>]
#   HEAD_INFO [HEAD=<name>]       print stored values
#   SET_PROBE_OFFSET [X= Y= Z=]   set probe offsets at runtime
#
# Status (usable in macros): printer.hermitcrab.active, .heads, .values
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from extras.hc_head import (
    ALL_KEYS,
    HEAD_NAME,
    HEAD_TEMPLATE,
    PID_KEYS,
    PROBE_KEYS,
    HCHead,
    fmt,
)

OPTION_LINE = re.compile(r"^([A-Za-z0-9_]+)\s*[:=]")
# Klipper stores pid_Kp/pid_Ki/pid_Kd multiplied by this factor in the controller
PID_PARAM_BASE = 255.0


def _read_lines(path: str) -> List[str]:
    with open(path) as f:
        return f.read().split("\n")


def _write_lines(path: str, lines: List[str]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write("\n".join(lines))
    os.replace(tmp, path)


def _section_bounds(lines: List[str], section: str) -> Optional[Tuple[int, int]]:
    """Return (header index, index after the section's last line)."""
    header = "[%s]" % section.lower()
    for start, line in enumerate(lines):
        if line.strip().lower() == header:
            end = start + 1
            while end < len(lines) and not lines[end].startswith("["):
                end += 1
            return start, end
    return None


def _append_section(lines: List[str], section: str, body: List[str]) -> List[str]:
    trimmed = list(lines)
    while trimmed and not trimmed[-1].strip():
        trimmed.pop()
    return trimmed + ["", "[%s]" % section] + body + [""]


def section_exists(path: str, section: str) -> bool:
    return _section_bounds(_read_lines(path), section) is not None


def set_section_options(path: str, section: str, updates: Dict[str, str]) -> None:
    """Set options in one section of a config file.

    An active option line is replaced in place. A commented placeholder such
    as "# x_offset: <mm>" keeps its text and the value is inserted below it.
    Other options are added at the end of the section. A missing section is
    appended to the file. Everything else in the file is left untouched.
    """
    lines = _read_lines(path)
    bounds = _section_bounds(lines, section)
    if bounds is None:
        body = ["%s: %s" % (k, updates[k]) for k in sorted(updates)]
        _write_lines(path, _append_section(lines, section, body))
        return

    start, end = bounds
    remaining = dict(updates)
    for j in range(start + 1, end):
        match = OPTION_LINE.match(lines[j])
        if match and match.group(1).lower() in remaining:
            key = match.group(1).lower()
            lines[j] = "%s: %s" % (key, remaining.pop(key))

    last = end - 1
    while last > start and not lines[last].strip():
        last -= 1
    inserts: Dict[int, List[str]] = {}
    for key in sorted(remaining):
        placeholder = re.compile(r"#\s*%s\s*[:=]" % re.escape(key), re.IGNORECASE)
        index = next(
            (j for j in range(start + 1, end) if placeholder.match(lines[j].lstrip())),
            last,
        )
        inserts.setdefault(index, []).append("%s: %s" % (key, remaining[key]))

    result: List[str] = []
    for j, line in enumerate(lines):
        result.append(line)
        result.extend(inserts.get(j, []))
    _write_lines(path, result)


STATE_SECTION = "hermitcrab state"


class HeadState:
    """The [hermitcrab state] section: the head applied last."""

    def __init__(self, config: Any) -> None:
        self.active: Optional[str] = config.get("active_head", None)


class HermitCrab:
    def __init__(self, config: Any) -> None:
        self.printer: Any = config.get_printer()
        self.reactor: Any = self.printer.get_reactor()
        self.gcode: Any = self.printer.lookup_object("gcode")
        self.path = self._resolve_path(config.get("file", "toolheads.cfg"))
        self.default_head: Optional[str] = config.get("default_head", None)
        self.heater: str = config.get("heater", "extruder")
        self.extruder: str = config.get("extruder", "extruder")
        self.pin_prefix: str = config.get("pin_prefix", "TOOLHEAD_")
        self.heads: Dict[str, HCHead] = {}
        self.active_mem: Optional[str] = None
        for name, handler, desc in (
            ("HC_SET_HEAD", self.cmd_SET_HEAD, "Apply a toolhead (HEAD=<name>)"),
            ("HC_SAVE_HEAD", self.cmd_SAVE_HEAD, "Store values in a toolhead section"),
            ("HC_ADD_HEAD", self.cmd_ADD_HEAD, "Add an empty toolhead (NAME=<name>)"),
            ("HC_HEAD_INFO", self.cmd_HEAD_INFO, "Show stored values of a toolhead"),
            (
                "HC_SET_PROBE_OFFSET",
                self.cmd_SET_PROBE_OFFSET,
                "Set probe X/Y/Z offset at runtime (re-home Z after changing Z)",
            ),
        ):
            self.gcode.register_command(name, handler, desc=desc)

    def _resolve_path(self, name: str) -> str:
        path = os.path.expanduser(name)
        if not os.path.isabs(path):
            config_file = self.printer.get_start_args()["config_file"]
            directory = os.path.dirname(os.path.abspath(config_file))
            path = os.path.join(directory, path)
        return path

    def add_head(self, head: HCHead) -> None:
        self.heads[head.name] = head

    # ---- active head (state lives in the [hermitcrab state] section) ----
    def _fallback_head(self) -> str:
        if self.default_head and self.default_head.lower() in self.heads:
            return self.default_head.lower()
        return sorted(self.heads)[0] if self.heads else ""

    def _active(self) -> str:
        state = self.printer.lookup_object(STATE_SECTION, None)
        name: Any = self.active_mem or (state.active if state else None)
        text = str(name).lower() if name else ""
        return text if text in self.heads else self._fallback_head()

    def _store_active(self, name: str) -> None:
        set_section_options(self.path, STATE_SECTION, {"active_head": name})

    def get_status(self, eventtime: float) -> Dict[str, Any]:
        active = self._active()
        head = self.heads.get(active)
        return {
            "active": active,
            "heads": sorted(self.heads),
            "values": dict(head.values) if head else {},
        }

    def _head_arg(self, gcmd: Any) -> HCHead:
        name = str(gcmd.get("HEAD", self._active())).lower()
        if name not in self.heads:
            raise gcmd.error(
                "Unknown head '%s' (known: %s)" % (name, ", ".join(sorted(self.heads)))
            )
        return self.heads[name]

    # ---- probe offsets ----
    def _set_probe(
        self, x: Optional[float], y: Optional[float], z: Optional[float]
    ) -> None:
        """None means: leave that axis unchanged."""
        probe = self.printer.lookup_object("probe")
        po = probe.probe_offsets
        if x is not None:
            po.x_offset = x
        if y is not None:
            po.y_offset = y
        if z is None:
            return
        po.z_offset = z
        # Z also lives in the endstop wrapper and in the Z rail
        wrapper = getattr(probe, "mcu_probe", None)
        if wrapper is not None and hasattr(wrapper, "position_endstop"):
            wrapper.position_endstop = z
        kin = self.printer.lookup_object("toolhead").get_kinematics()
        rail = kin.rails[2]
        rail.position_endstop = z
        # older versions cache the tuple, newer ones build it on demand
        if hasattr(rail, "homing_info"):
            rail.homing_info = rail.homing_info._replace(position_endstop=z)

    # ---- PID (runtime controller values, same units as the config) ----
    def _set_pid(self, kp: float, ki: float, kd: float) -> None:
        heaters = self.printer.lookup_object("heaters")
        heater = heaters.lookup_heater(self.heater)
        with heater.lock:
            control = heater.control
            if not hasattr(control, "Kp"):
                raise ValueError("heater %s does not use PID control" % self.heater)
            control.Kp = kp / PID_PARAM_BASE
            control.Ki = ki / PID_PARAM_BASE
            control.Kd = kd / PID_PARAM_BASE

    def cmd_SET_PROBE_OFFSET(self, gcmd: Any) -> None:
        try:
            x = gcmd.get_float("X", None)
            y = gcmd.get_float("Y", None)
            z = gcmd.get_float("Z", None)
            self._set_probe(x, y, z)
        except Exception as e:
            raise gcmd.error("SET_PROBE_OFFSET failed: %s: %s" % (type(e).__name__, e))
        po = self.printer.lookup_object("probe").probe_offsets
        msg = "Probe offsets: X=%.3f Y=%.3f Z=%.3f" % (
            po.x_offset,
            po.y_offset,
            po.z_offset,
        )
        if z is not None:
            msg += " - run G28 Z now"
        gcmd.respond_raw(msg)

    # ---- SET_HEAD ----
    def cmd_SET_HEAD(self, gcmd: Any) -> None:
        head = self._head_arg(gcmd)
        v = head.values

        # 0. store the active head before applying anything, so a failed write
        # leaves the printer unchanged
        if head.name != self._active():
            try:
                self._store_active(head.name)
            except (IOError, OSError) as e:
                raise gcmd.error("Cannot write %s: %s" % (self.path, e))

        # 1. probe offsets (real ones, no G-code offset trick)
        if head.has_probe():
            try:
                self._set_probe(*[head.get(k) for k in PROBE_KEYS])
            except Exception as e:
                raise gcmd.error(
                    "Setting probe offsets failed: %s: %s" % (type(e).__name__, e)
                )

        # 2. PID (only if all three values exist and kp is valid)
        if head.has_pid():
            try:
                self._set_pid(v["pid_kp"], v["pid_ki"], v["pid_kd"])
            except Exception as e:
                raise gcmd.error("Setting PID failed: %s: %s" % (type(e).__name__, e))

        # 3. optional extruder tuning
        if "pressure_advance" in v:
            self._run(
                "SET_PRESSURE_ADVANCE EXTRUDER=%s ADVANCE=%.4f SMOOTH_TIME=%.3f"
                % (self.extruder, v["pressure_advance"], v.get("pa_smooth_time", 0.04))
            )
        if "rotation_distance" in v:
            self._run(
                "SET_EXTRUDER_ROTATION_DISTANCE EXTRUDER=%s DISTANCE=%.5f"
                % (self.extruder, v["rotation_distance"])
            )

        # 4. remember head, switch status pins (only pins that exist), display
        self.active_mem = head.name
        for name in sorted(self.heads):
            pin = "%s%s" % (self.pin_prefix, name.upper())
            if self.printer.lookup_object("output_pin " + pin, None) is not None:
                self._run("SET_PIN PIN=%s VALUE=%d" % (pin, int(name == head.name)))
        self._run("M117 Toolhead: %s" % head.name.upper())

        gcmd.respond_raw("=== Toolhead %s loaded ===" % head.name.upper())
        gcmd.respond_raw(head.format())

    def _run(self, script: str) -> None:
        self.gcode.run_script_from_command(script)

    # ---- SAVE_HEAD ----
    def cmd_SAVE_HEAD(self, gcmd: Any) -> None:
        head = self._head_arg(gcmd)
        new: Dict[str, float] = {}
        if head.name == self._active():
            # runtime values and pending calibration belong to the active head
            po = self.printer.lookup_object("probe").probe_offsets
            new.update(x_offset=po.x_offset, y_offset=po.y_offset, z_offset=po.z_offset)
            cfg = self.printer.lookup_object("configfile")
            pending = getattr(cfg, "status_save_pending", {})
            if "z_offset" in pending.get("probe", {}):
                new["z_offset"] = float(pending["probe"]["z_offset"])
            pid_pending = {
                k.lower(): v for k, v in pending.get(self.heater, {}).items()
            }
            for k in PID_KEYS:
                if k in pid_pending:
                    new[k] = float(pid_pending[k])
        # explicit values: SAVE_HEAD HEAD=willi Z_OFFSET=0.1 PID_KP=40 ...
        for k in ALL_KEYS:
            value = gcmd.get_float(k.upper(), None)
            if value is not None:
                new[k] = value

        changed: Dict[str, float] = {}
        for k, value in new.items():
            stored = float(fmt(value))
            current = head.get(k)
            if current is None or abs(current - stored) > 1e-9:
                changed[k] = stored
        if not changed:
            gcmd.respond_raw("Head %s: nothing to store" % head.name.upper())
            return
        try:
            set_section_options(
                self.path,
                "hc_head %s" % head.name,
                {k: fmt(v) for k, v in changed.items()},
            )
        except (IOError, OSError) as e:
            raise gcmd.error("Cannot write %s: %s" % (self.path, e))
        for k, value in changed.items():
            head.set(k, value)
        gcmd.respond_raw("Head %s stored in %s:" % (head.name.upper(), self.path))
        gcmd.respond_raw(head.format(changed))

    # ---- ADD_HEAD ----
    def cmd_ADD_HEAD(self, gcmd: Any) -> None:
        name = gcmd.get("NAME").strip().lower()
        if not HEAD_NAME.match(name):
            raise gcmd.error(
                "Invalid head name '%s': use lowercase letters, digits or '_', "
                "starting with a letter or digit" % name
            )
        upper = name.upper()
        blocks = [
            ("hc_head %s" % name, list(HEAD_TEMPLATE)),
            (
                "output_pin %s%s" % (self.pin_prefix, upper),
                ["pin: virtual_pin:head_%s" % name, "value: 0"],
            ),
            (
                "gcode_macro USE_HEAD_%s" % upper,
                [
                    "description: Switch to toolhead %s" % upper,
                    "gcode:",
                    "    HC_SET_HEAD HEAD=%s" % name,
                ],
            ),
        ]
        try:
            if name in self.heads or section_exists(self.path, blocks[0][0]):
                raise gcmd.error("Head '%s' already exists" % name)
            lines = _read_lines(self.path)
            for section, _ in blocks:
                if _section_bounds(lines, section) is not None:
                    raise gcmd.error(
                        "Section [%s] already exists in %s" % (section, self.path)
                    )
            for section, body in blocks:
                lines = _append_section(lines, section, body)
            _write_lines(self.path, lines)
        except (IOError, OSError) as e:
            raise gcmd.error("Cannot write %s: %s" % (self.path, e))
        self.add_head(HCHead(name))
        gcmd.respond_raw(
            "Head %s added to %s with pin %s%s and macro USE_HEAD_%s. "
            "Store values with SAVE_HEAD HEAD=%s."
            % (upper, self.path, self.pin_prefix, upper, upper, name)
        )

    # ---- HEAD_INFO ----
    def cmd_HEAD_INFO(self, gcmd: Any) -> None:
        head = self._head_arg(gcmd)
        gcmd.respond_raw(
            "--- Stored values for '%s' ---\n%s" % (head.name, head.format())
        )


def load_config(config: Any) -> HermitCrab:
    return HermitCrab(config)


def load_config_prefix(config: Any) -> HeadState:
    return HeadState(config)
