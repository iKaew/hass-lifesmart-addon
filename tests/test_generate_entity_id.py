import ast
import importlib.util
import types
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_generate_entity_id():
    """Load generate_entity_id from project without Home Assistant deps."""
    # Stub minimal modules required for const
    ha_const = types.ModuleType("homeassistant.const")
    class Platform:
        SWITCH = "switch"
        BINARY_SENSOR = "binary_sensor"
        SENSOR = "sensor"
        COVER = "cover"
        LIGHT = "light"
        CLIMATE = "climate"
    ha_const.Platform = Platform
    sys.modules.setdefault("homeassistant.const", ha_const)
    sys.modules.setdefault("homeassistant.components", types.ModuleType("homeassistant.components"))
    climate_mod = types.ModuleType("homeassistant.components.climate")
    hvac = types.SimpleNamespace(
        OFF="off",
        AUTO="auto",
        FAN_ONLY="fan_only",
        COOL="cool",
        HEAT="heat",
        DRY="dry",
    )
    climate_mod.const = types.SimpleNamespace(HVACMode=hvac)
    sys.modules.setdefault("homeassistant.components.climate", climate_mod)

    # Load const module
    const_path = ROOT / "custom_components" / "lifesmart" / "const.py"
    spec = importlib.util.spec_from_file_location("lifesmart_const", const_path)
    const_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(const_mod)

    # Extract required functions from __init__.py
    init_path = ROOT / "custom_components" / "lifesmart" / "__init__.py"
    src = init_path.read_text()
    module_ast = ast.parse(src)
    code = ""
    for node in module_ast.body:
        if isinstance(node, ast.FunctionDef) and node.name in {
            "get_platform_by_device",
            "generate_entity_id",
        }:
            code += ast.get_source_segment(src, node) + "\n"
    namespace = const_mod.__dict__.copy()
    namespace["Platform"] = Platform
    exec(code, namespace)
    return namespace["generate_entity_id"]


def test_switch_with_subdevice():
    gen = load_generate_entity_id()
    assert (
        gen("SL_S", "HUB__1-2", "DEV1", "L1")
        == "switch.sl_s_hub_1_2_dev1_l1"
    )


def test_cover_device():
    gen = load_generate_entity_id()
    assert gen("SL_DOOYA", "HUB1", "CURTAIN") == "cover.sl_dooya_hub1_curtain"


def test_light_dimmer():
    gen = load_generate_entity_id()
    assert gen("SL_LI_WW", "HUB1", "LIGHT1") == "light.sl_li_ww_hub1_light1_p1p2"
