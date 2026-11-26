# [hc_head <name>] sections. Each section is one HCHead object, registered
# with the [hermitcrab] manager (see hermitcrab.py).
from typing import Any, Dict, Optional, Tuple
import re

PROBE_KEYS = ("x_offset", "y_offset", "z_offset")
PID_KEYS = ("pid_kp", "pid_ki", "pid_kd")
EXTRA_KEYS = (
    "probe_deploy_angle",
    "probe_stow_angle",
    "pressure_advance",
    "pa_smooth_time",
    "rotation_distance",
)
ALL_KEYS = PROBE_KEYS + PID_KEYS + EXTRA_KEYS
HEAD_NAME = re.compile(r"^[a-z0-9][a-z0-9_]*$")
LOGOS: Dict[str, Tuple[str, ...]] = {
    "crab": ("  ,-.       ,-.", "(   )-----(   )", " `-' (o o) `-'", "   /\\/\\_/\\/\\"),
    "cat": (" /\\_/\\", "( o.o )", " > ^ <"),
}
HEAD_TEMPLATE = (
    "# Probe offsets are applied to [probe] when this head is selected.",
    "# x_offset: <mm>",
    "# y_offset: <mm>",
    "# z_offset: <mm>",
    "# Heater PID values for [extruder]; applied only when all three are set.",
    "# pid_kp: <float>",
    "# pid_ki: <float>",
    "# pid_kd: <float>",
    "# Extruder tuning applied by SET_HEAD when set.",
    "# pressure_advance: <float>",
    "# pa_smooth_time: <s>, default 0.040, used with pressure_advance",
    "# rotation_distance: <float>",
    "# Stored for macros only; SET_HEAD does not apply these.",
    "# probe_deploy_angle: <deg>",
    "# probe_stow_angle: <deg>",
    "# Logo shown by SET_HEAD and HEAD_INFO: crab, cat or custom.",
    "# logo: <crab|cat|custom>",
    "# logo_custom: <art lines separated by |, used with logo: custom>",
)


def fmt(value: float) -> str:
    text = ("%.4f" % value).rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def load_logo(config: Any) -> Tuple[str, ...]:
    kind = config.get("logo", None)
    if kind is None:
        return ()
    kind = kind.strip().lower()
    if kind in LOGOS:
        return LOGOS[kind]
    if kind != "custom":
        raise config.error("Unknown logo '%s': use crab, cat or custom" % kind)
    custom = config.get("logo_custom", None)
    if not custom:
        raise config.error("logo: custom needs logo_custom")
    return tuple(line.rstrip() for line in custom.split("|"))


class HCHead:
    """One toolhead and the values stored for it."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.values: Dict[str, float] = {}
        self.logo: Tuple[str, ...] = ()

    def get(self, key: str) -> Optional[float]:
        return self.values.get(key)

    def set(self, key: str, value: float) -> None:
        self.values[key] = value

    def has_probe(self) -> bool:
        return any(k in self.values for k in PROBE_KEYS)

    def has_pid(self) -> bool:
        return all(k in self.values for k in PID_KEYS) and self.values["pid_kp"] > 0

    def format(self, values: Optional[Dict[str, float]] = None) -> str:
        shown = self.values if values is None else values
        lines = [
            "  [hc_head %s] %s: %s" % (self.name, k, fmt(shown[k]))
            for k in sorted(shown)
        ]
        if values is None:
            lines = ["  " + line for line in self.logo] + lines
        return "\n".join(lines)


def load_config_prefix(config: Any) -> None:
    name = config.get_name().split(None, 1)[1].strip().lower()
    head = HCHead(name)
    for key in ALL_KEYS:
        value = config.getfloat(key, None)
        if value is not None:
            head.set(key, value)
    head.logo = load_logo(config)
    config.get_printer().load_object(config, "hermitcrab").add_head(head)
