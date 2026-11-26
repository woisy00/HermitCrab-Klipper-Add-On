from pathlib import Path
from typing import Any, Dict, Optional

import pytest

from extras.hermitcrab import HermitCrab


class FakeGCode:
    def __init__(self) -> None:
        self.commands: Dict[str, Any] = {}
        self.scripts = []

    def register_command(self, command: str, callback: Any, desc: Any = None) -> None:
        self.commands[command] = callback

    def run_script(self, script: str) -> None:
        self.scripts.append(script)


class FakeCommand:
    def __init__(self, params: Optional[Dict[str, str]] = None) -> None:
        self.params = params or {}
        self.messages = []

    def get(self, name: str, default: Optional[str] = None) -> Optional[str]:
        return self.params.get(name, default)

    def error(self, message: str) -> Exception:
        return RuntimeError(message)

    def respond_info(self, message: str) -> None:
        self.messages.append(message)


class FakeStatusObject:
    def __init__(self, status: Dict[str, Any]) -> None:
        self.status = status

    def get_status(self, eventtime: float) -> Dict[str, Any]:
        return self.status


class FakeReactor:
    def monotonic(self) -> float:
        return 0.0


class FakePrinter:
    def __init__(self, config_file: Path, pending: Dict[str, Any]) -> None:
        self.gcode = FakeGCode()
        self.objects = {
            "gcode": self.gcode,
            "configfile": FakeStatusObject(
                {
                    "save_config_pending": bool(pending),
                    "save_config_pending_items": pending,
                }
            ),
        }
        self.config_file = config_file

    def get_start_args(self) -> Dict[str, Any]:
        return {"config_file": str(self.config_file)}

    def lookup_object(self, name: str, default: Any = None) -> Any:
        return self.objects.get(name, default)

    def get_reactor(self) -> FakeReactor:
        return FakeReactor()


class FakeConfig:
    def __init__(self, printer: FakePrinter) -> None:
        self.printer = printer

    def get(self, key: str, default: Optional[str] = None) -> str:
        return default or ""

    def get_printer(self) -> FakePrinter:
        return self.printer

    def error(self, message: str) -> Exception:
        return RuntimeError(message)


def make_plugin(tmp_path: Path, pending: Optional[Dict[str, Any]] = None) -> HermitCrab:
    config_directory = tmp_path / "printer_data" / "config"
    toolheads = config_directory / "toolheads"
    toolheads.mkdir(parents=True)
    shared = config_directory / "shared"
    shared.mkdir()
    (shared / "hardware.cfg").write_text(
        "[probe]\npin: ^PA1\n\n[extruder]\nheater_pin: PA2\n",
        encoding="utf-8",
    )
    base_defaults = toolheads / "defaults"
    base_defaults.mkdir()
    (toolheads / "base.cfg").write_text(
        "[include defaults/toolhead.cfg]\n",
        encoding="utf-8",
    )
    (toolheads / "active.cfg").touch()
    (base_defaults / "toolhead.cfg").write_text(
        "[probe]\nz_offset: 0.1 ; default probe offset\n\n"
        "[extruder]\npid_Kp: 10.0\n"
        "#*# <---------------------- SAVE_CONFIG ---------------------->\n"
        "#*# [probe]\n"
        "#*# z_offset = 0.1\n",
        encoding="utf-8",
    )
    config_file = config_directory / "printer.cfg"
    config_file.write_text(
        "[include shared/hardware.cfg]\n"
        "[include toolheads/base.cfg]\n"
        "[include toolheads/active.cfg]\n",
        encoding="utf-8",
    )
    printer = FakePrinter(config_file, pending or {})
    return HermitCrab(FakeConfig(printer))


def test_set_active_head_links_profile_and_restarts(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)
    profile = plugin.toolheads_directory / "tool0.cfg"
    profile.write_text("[probe]\nz_offset: 0.2\n", encoding="utf-8")

    command = FakeCommand({"HEAD": "tool0"})
    plugin.cmd_SET_ACTIVE_HEAD(command)

    assert plugin._active_head() == "tool0"
    assert plugin.get_status(0.0)["available_heads"] == ["tool0"]
    assert plugin.gcode.scripts == ["RESTART"]


def test_store_active_head_values_preserves_profile_content(
    tmp_path: Path,
) -> None:
    pending = {
        "probe": {"z_offset": "0.35"},
        "extruder": {"pid_Kp": "21.4", "pid_Ki": "1.1", "pid_Kd": "105.0"},
    }
    plugin = make_plugin(tmp_path, pending)
    profile = plugin.toolheads_directory / "tool0.cfg"
    profile.write_text(
        "# toolhead-specific settings\n[probe]\nx_offset: 1.0\nz_offset: 0.35\n",
        encoding="utf-8",
    )
    active_config = plugin.toolheads_directory / "active.cfg"
    active_config.unlink()
    active_config.symlink_to(profile.name)

    sources = plugin._read_config_sources(profile)
    assert sources.merged_values["probe"]["z_offset"] == "0.35"

    plugin.cmd_STORE_ACTIVE_HEAD(FakeCommand())
    contents = profile.read_text(encoding="utf-8")
    shared_defaults = (
        plugin.toolheads_directory / "defaults" / "toolhead.cfg"
    ).read_text(encoding="utf-8")

    assert "# toolhead-specific settings" in contents
    assert "x_offset: 1.0" in contents
    assert "[probe]\nz_offset: 0.35" in contents
    assert "[extruder]" in contents
    assert "pid_Kp: 21.4" in contents
    assert contents.count("# BEGIN HERMITCRAB STORED VALUES") == 1
    assert "z_offset: 0.35" in shared_defaults
    assert "z_offset: 0.35 ; default probe offset" in shared_defaults
    assert "pid_Kp: 21.4" in shared_defaults
    assert shared_defaults.index("pid_Ki: 1.1") < shared_defaults.index(
        "#*# <---------------------- SAVE_CONFIG"
    )
    assert plugin.gcode.scripts == ["RESTART"]

    plugin.printer.objects["configfile"].status = {
        "save_config_pending": True,
        "save_config_pending_items": {"probe": {"z_offset": "0.42"}},
    }
    plugin.cmd_STORE_ACTIVE_HEAD(FakeCommand())
    contents = profile.read_text(encoding="utf-8")
    shared_defaults = (
        plugin.toolheads_directory / "defaults" / "toolhead.cfg"
    ).read_text(encoding="utf-8")

    assert contents.count("# BEGIN HERMITCRAB STORED VALUES") == 1
    managed_values = contents.split("# BEGIN HERMITCRAB STORED VALUES", 1)[
        1
    ].split("# END HERMITCRAB STORED VALUES", 1)[0]
    assert "z_offset: 0.42" in managed_values
    assert "z_offset: 0.35" not in managed_values
    assert "z_offset: 0.42" in shared_defaults


def test_store_active_head_rejects_unrelated_pending_values(
    tmp_path: Path,
) -> None:
    plugin = make_plugin(
        tmp_path, {"stepper_x": {"position_min": "-1"}}
    )
    profile = plugin.toolheads_directory / "tool0.cfg"
    profile.write_text("[probe]\nz_offset: 0.2\n", encoding="utf-8")
    active_config = plugin.toolheads_directory / "active.cfg"
    active_config.unlink()
    active_config.symlink_to(profile.name)
    before = profile.read_text(encoding="utf-8")

    with pytest.raises(RuntimeError, match="cannot store pending settings"):
        plugin.cmd_STORE_ACTIVE_HEAD(FakeCommand())

    assert profile.read_text(encoding="utf-8") == before
    assert plugin.gcode.scripts == []


def test_set_active_head_refuses_active_virtual_sd_print(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)
    profile = plugin.toolheads_directory / "tool0.cfg"
    profile.write_text("[probe]\nz_offset: 0.2\n", encoding="utf-8")
    plugin.printer.objects["virtual_sdcard"] = FakeStatusObject(
        {"is_active": True}
    )

    with pytest.raises(RuntimeError, match="virtual SD print is active"):
        plugin.cmd_SET_ACTIVE_HEAD(FakeCommand({"HEAD": "tool0"}))

    assert not (plugin.toolheads_directory / "active.cfg").is_symlink()
    assert plugin.gcode.scripts == []


def test_base_profile_must_be_included_before_active_profile(
    tmp_path: Path,
) -> None:
    plugin = make_plugin(tmp_path)
    plugin.config_file.write_text(
        "[include toolheads/active.cfg]\n"
        "[include toolheads/base.cfg]\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="base.cfg before"):
        HermitCrab(FakeConfig(FakePrinter(plugin.config_file, {})))
