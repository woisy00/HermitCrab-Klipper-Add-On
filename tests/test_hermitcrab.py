from pathlib import Path
import threading
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

from extras.hc_head import HCHead, load_config_prefix
from extras.hermitcrab import HermitCrab, set_section_options


class FakeGCode:
    def __init__(self) -> None:
        self.commands: Dict[str, Any] = {}

    def register_command(self, command: str, callback: Any, desc: Any = None) -> None:
        self.commands[command] = callback


class FakeCommand:
    def __init__(self, params: Dict[str, str]) -> None:
        self.params = params
        self.messages: List[str] = []

    def get(self, name: str, default: Optional[str] = None) -> Any:
        if name in self.params:
            return self.params[name]
        if default is None:
            raise KeyError(name)
        return default

    def get_float(self, name: str, default: Any = None) -> Any:
        return float(self.params[name]) if name in self.params else default

    def error(self, message: str) -> Exception:
        return RuntimeError(message)

    def respond_raw(self, message: str) -> None:
        self.messages.append(message)


class FakePrinter:
    def __init__(self, config_file: Path) -> None:
        self.gcode = FakeGCode()
        self.config_file = config_file

    def get_start_args(self) -> Dict[str, Any]:
        return {"config_file": str(self.config_file)}

    def lookup_object(self, name: str, default: Any = None) -> Any:
        return self.gcode if name == "gcode" else default

    def get_reactor(self) -> Any:
        return None

    def load_object(self, config: Any, name: str) -> "HermitCrab":
        return self.manager


class FakeConfig:
    def __init__(self, printer: FakePrinter, name: str, values: Dict[str, str]) -> None:
        self.printer = printer
        self.name = name
        self.values = values

    def get_name(self) -> str:
        return self.name

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def getfloat(self, key: str, default: Any = None) -> Any:
        return float(self.values[key]) if key in self.values else default

    def get_printer(self) -> FakePrinter:
        return self.printer

    def error(self, msg: str) -> RuntimeError:
        return RuntimeError(msg)


def make_manager(tmp_path: Path, text: str) -> HermitCrab:
    config_file = tmp_path / "printer.cfg"
    config_file.write_text(text)
    (tmp_path / "toolheads.cfg").write_text("")
    printer = FakePrinter(config_file)
    manager = HermitCrab(FakeConfig(printer, "hermitcrab", {"file": "toolheads.cfg"}))
    printer.manager = manager
    return manager


def test_set_section_options_fills_placeholder_and_replaces_active_lines(
    tmp_path: Path,
) -> None:
    path = tmp_path / "toolheads.cfg"
    path.write_text(
        "[hc_head emil]\n"
        "# x_offset: <mm>\n"
        "# z_offset: <mm>\n"
        "pid_kp: 1.0\n"
        "\n"
        "[hc_head willi]\n"
        "z_offset: 0.1\n"
    )

    set_section_options(
        str(path), "hc_head emil", {"x_offset": "-35", "pid_kp": "41.3"}
    )

    assert path.read_text() == (
        "[hc_head emil]\n"
        "# x_offset: <mm>\n"
        "x_offset: -35\n"
        "# z_offset: <mm>\n"
        "pid_kp: 41.3\n"
        "\n"
        "[hc_head willi]\n"
        "z_offset: 0.1\n"
    )


def test_set_section_options_appends_missing_section(tmp_path: Path) -> None:
    path = tmp_path / "toolheads.cfg"
    path.write_text("[hc_head emil]\nz_offset: 0.4\n")

    set_section_options(str(path), "hc_head willi", {"z_offset": "0.1"})

    assert path.read_text() == (
        "[hc_head emil]\nz_offset: 0.4\n\n[hc_head willi]\nz_offset: 0.1\n"
    )


def test_add_head_appends_commented_template_and_rejects_duplicates(
    tmp_path: Path,
) -> None:
    manager = make_manager(tmp_path, "[hermitcrab]\nfile: toolheads.cfg\n")
    path = tmp_path / "toolheads.cfg"
    add_head = manager.gcode.commands["HC_ADD_HEAD"]

    add_head(FakeCommand({"NAME": "Emil"}))
    text = path.read_text()
    assert text.startswith("\n[hc_head emil]\n# Probe offsets")
    assert "\n# x_offset: <mm>\n" in text
    assert "# pid_kp: <float>" in text
    assert "# probe_stow_angle: <deg>" in text
    assert "\n[output_pin TOOLHEAD_EMIL]\npin: virtual_pin:head_emil\nvalue: 0\n" in text
    assert "\n[gcode_macro USE_HEAD_EMIL]\n" in text
    assert "    HC_SET_HEAD HEAD=emil\n" in text

    with pytest.raises(RuntimeError, match="already exists"):
        add_head(FakeCommand({"NAME": "emil"}))


def test_add_head_refuses_existing_pin_or_macro(tmp_path: Path) -> None:
    manager = make_manager(tmp_path, "[hermitcrab]\nfile: toolheads.cfg\n")
    path = tmp_path / "toolheads.cfg"
    path.write_text("[output_pin TOOLHEAD_WILLI]\npin: virtual_pin:head_willi\n")
    before = path.read_text()
    with pytest.raises(RuntimeError, match=r"\[output_pin TOOLHEAD_WILLI\] already"):
        manager.gcode.commands["HC_ADD_HEAD"](FakeCommand({"NAME": "willi"}))
    assert path.read_text() == before


def test_add_head_rejects_invalid_name(tmp_path: Path) -> None:
    manager = make_manager(tmp_path, "[hermitcrab]\n")
    with pytest.raises(RuntimeError, match="Invalid head name"):
        manager.gcode.commands["HC_ADD_HEAD"](FakeCommand({"NAME": "bad name"}))
    with pytest.raises(RuntimeError, match="Invalid head name"):
        manager.gcode.commands["HC_ADD_HEAD"](FakeCommand({"NAME": "bad-name"}))


def test_set_pid_applies_config_units_to_heater_controller(tmp_path: Path) -> None:
    manager = make_manager(tmp_path, "[hermitcrab]\nfile: toolheads.cfg\n")
    control = SimpleNamespace(Kp=0.0, Ki=0.0, Kd=0.0)
    heater = SimpleNamespace(lock=threading.Lock(), control=control)
    heaters = SimpleNamespace(lookup_heater=lambda name: heater)
    manager.printer = SimpleNamespace(lookup_object=lambda name: heaters)

    manager._set_pid(255.0, 25.5, 510.0)

    assert control.Kp == pytest.approx(1.0)
    assert control.Ki == pytest.approx(0.1)
    assert control.Kd == pytest.approx(2.0)


def test_head_loader_registers_only_configured_values(tmp_path: Path) -> None:
    manager = make_manager(tmp_path, "[hermitcrab]\n")
    printer = manager.printer
    config = FakeConfig(
        printer, "hc_head Emil", {"x_offset": "-35", "pid_kp": "41.346"}
    )

    load_config_prefix(config)

    assert list(manager.heads) == ["emil"]
    head = manager.heads["emil"]
    assert isinstance(head, HCHead)
    assert head.values == {"x_offset": -35.0, "pid_kp": 41.346}


def test_head_logo_predefined_custom_and_errors(tmp_path: Path) -> None:
    manager = make_manager(tmp_path, "[hermitcrab]\n")
    printer = manager.printer

    load_config_prefix(FakeConfig(printer, "hc_head cat", {"logo": "Cat"}))
    assert manager.heads["cat"].logo == (" /\\_/\\", "( o.o )", " > ^ <")

    custom = {"logo": "custom", "logo_custom": " /|\\ |  o  "}
    load_config_prefix(FakeConfig(printer, "hc_head mine", custom))
    assert manager.heads["mine"].logo == (" /", "\\", "  o")

    with pytest.raises(RuntimeError, match="needs logo_custom"):
        load_config_prefix(FakeConfig(printer, "hc_head bad", {"logo": "custom"}))
    with pytest.raises(RuntimeError, match="Unknown logo"):
        load_config_prefix(FakeConfig(printer, "hc_head bad2", {"logo": "dog"}))


def test_format_shows_logo_only_in_full_output(tmp_path: Path) -> None:
    manager = make_manager(tmp_path, "[hermitcrab]\n")
    load_config_prefix(
        FakeConfig(manager.printer, "hc_head emil", {"logo": "crab", "x_offset": "-35"})
    )
    head = manager.heads["emil"]

    full = head.format()
    assert full.startswith("    ,-.       ,-.\n")
    assert full.endswith("  [hc_head emil] x_offset: -35")
    assert head.format({"x_offset": -35.0}) == "  [hc_head emil] x_offset: -35"
