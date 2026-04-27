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
        REMOTE = "remote"
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


def test_motion_sensor_device():
    gen = load_generate_entity_id()
    assert gen("SL_SC_MHW", "HUB1", "MOTION1", "M") == (
        "binary_sensor.sl_sc_mhw_hub1_motion1_m"
    )


def test_water_leak_sensor_device():
    gen = load_generate_entity_id()
    assert gen("SL_SC_WA", "HUB1", "WATER1", "WA") == (
        "binary_sensor.sl_sc_wa_hub1_water1_wa"
    )


def test_water_leak_battery_sensor_device():
    gen = load_generate_entity_id()
    assert gen("SL_SC_WA", "HUB1", "WATER1", "V") == (
        "sensor.sl_sc_wa_hub1_water1_v"
    )


def test_co2_sensor_device():
    gen = load_generate_entity_id()
    assert gen("SL_SC_CA", "HUB1", "CO21", "P3") == (
        "sensor.sl_sc_ca_hub1_co21_p3"
    )


def test_radar_motion_sensor_device():
    gen = load_generate_entity_id()
    assert gen("SL_P_RM", "HUB1", "RADAR1", "P1") == (
        "binary_sensor.sl_p_rm_hub1_radar1_p1"
    )


def test_defed_door_sensor_device():
    gen = load_generate_entity_id()
    assert gen("SL_DF_GG", "HUB1", "DOOR1", "GA") == (
        "binary_sensor.sl_df_gg_hub1_door1_ga"
    )


def test_defed_battery_sensor_device():
    gen = load_generate_entity_id()
    assert gen("SL_DF_MM", "HUB1", "MOTION1", "V") == (
        "sensor.sl_df_mm_hub1_motion1_v"
    )


def test_garage_door_device():
    gen = load_generate_entity_id()
    assert gen("SL_ETDOOR", "HUB1", "GARAGE1") == (
        "cover.sl_etdoor_hub1_garage1"
    )


def test_smoke_battery_sensor_device():
    gen = load_generate_entity_id()
    assert gen("SL_P_A", "HUB1", "SMOKE1", "P2") == (
        "sensor.sl_p_a_hub1_smoke1_p2"
    )


def test_defed_siren_device():
    gen = load_generate_entity_id()
    assert gen("SL_DF_SR", "HUB1", "SIREN1", "SR") == (
        "binary_sensor.sl_df_sr_hub1_siren1_sr"
    )


def test_defed_keyfob_device():
    gen = load_generate_entity_id()
    assert gen("SL_DF_BB", "HUB1", "KEYFOB1", "eB1") == (
        "binary_sensor.sl_df_bb_hub1_keyfob1_eb1"
    )


def test_noise_sensor_device():
    gen = load_generate_entity_id()
    assert gen("SL_SC_CN", "HUB1", "NOISE1", "P1") == (
        "sensor.sl_sc_cn_hub1_noise1_p1"
    )


def test_noise_buzzer_device():
    gen = load_generate_entity_id()
    assert gen("SL_SC_CN", "HUB1", "NOISE1", "P3") == (
        "binary_sensor.sl_sc_cn_hub1_noise1_p3"
    )


def test_gas_alarm_sound_device():
    gen = load_generate_entity_id()
    assert gen("SL_SC_CP", "HUB1", "GAS1", "P3") == (
        "binary_sensor.sl_sc_cp_hub1_gas1_p3"
    )


def test_smart_alarm_device():
    gen = load_generate_entity_id()
    assert gen("SL_ALM", "HUB1", "ALARM1", "P1") == (
        "binary_sensor.sl_alm_hub1_alarm1_p1"
    )


def test_env_sensor_device():
    gen = load_generate_entity_id()
    assert gen("SL_SC_THL", "HUB1", "ENV1", "T") == (
        "sensor.sl_sc_thl_hub1_env1_t"
    )


def test_tvoc_co2_sensor_device():
    gen = load_generate_entity_id()
    assert gen("SL_SC_CQ", "HUB1", "AIR1", "P4") == (
        "sensor.sl_sc_cq_hub1_air1_p4"
    )


def test_eliq_meter_device():
    gen = load_generate_entity_id()
    assert gen("ELIQ_EM", "HUB1", "METER1", "EPA") == (
        "sensor.eliq_em_hub1_meter1_epa"
    )


def test_air_purifier_switch_device():
    gen = load_generate_entity_id()
    assert gen("OD_MFRESH_M8088", "HUB1", "PURIFIER1", "O") == (
        "switch.od_mfresh_m8088_hub1_purifier1_o"
    )


def test_air_purifier_sensor_device():
    gen = load_generate_entity_id()
    assert gen("OD_MFRESH_M8088", "HUB1", "PURIFIER1", "PM") == (
        "sensor.od_mfresh_m8088_hub1_purifier1_pm"
    )


def test_c100_door_lock_battery_device():
    gen = load_generate_entity_id()
    assert gen("SL_LK_TY", "HUB1", "LOCK1", "BAT") == (
        "sensor.sl_lk_ty_hub1_lock1_bat"
    )


def test_c200_door_lock_doorbell_device():
    gen = load_generate_entity_id()
    assert gen("SL_LK_DJ", "HUB1", "LOCK1", "EVTBELL") == (
        "binary_sensor.sl_lk_dj_hub1_lock1_evtbell"
    )


def test_ha_controller_switch_device():
    gen = load_generate_entity_id()
    assert gen("SL_JEMA", "HUB1", "CTRL1", "P8") == (
        "switch.sl_jema_hub1_ctrl1_p8"
    )


def test_ha_controller_status_device():
    gen = load_generate_entity_id()
    assert gen("SL_JEMA", "HUB1", "CTRL1", "P5") == (
        "binary_sensor.sl_jema_hub1_ctrl1_p5"
    )


def test_dlt_meter_energy_device():
    gen = load_generate_entity_id()
    assert gen("V_DLT_645_P", "HUB1", "METER1", "EE") == (
        "sensor.v_dlt_645_p_hub1_meter1_ee"
    )


def test_dlt_meter_appendix_alias_device():
    gen = load_generate_entity_id()
    assert gen("V_DLT645_P", "HUB1", "METER1", "EP") == (
        "sensor.v_dlt645_p_hub1_meter1_ep"
    )


def test_485_controller_switch_device():
    gen = load_generate_entity_id()
    assert gen("V_485_P", "HUB1", "CTRL1", "L1") == (
        "switch.v_485_p_hub1_ctrl1_l1"
    )


def test_485_controller_power_device():
    gen = load_generate_entity_id()
    assert gen("V_485_P", "HUB1", "CTRL1", "EP") == (
        "sensor.v_485_p_hub1_ctrl1_ep"
    )


def test_nature_temperature_sensor():
    gen = load_generate_entity_id()
    assert gen("SL_NATURE", "HUB1", "NATURE1", "P4") == (
        "sensor.sl_nature_hub1_nature1_p4"
    )


def test_nature_thermostat_climate():
    gen = load_generate_entity_id()
    assert gen("SL_NATURE", "HUB:1", "NATURE@1", "climate") == (
        "climate.sl_nature_hub_1_nature_1_thermostat"
    )


def test_climate_device():
    gen = load_generate_entity_id()
    assert gen("V_AIR_P", "HUB:1", "AIR@1") == "climate.v_air_p_hub_1_air_1"


def test_v_air_p_reference_climate_device():
    gen = load_generate_entity_id()
    assert (
        gen("V_T8600_P", "HUB:1", "AIR@1")
        == "climate.v_t8600_p_hub_1_air_1"
    )


def test_spot_remote_device():
    gen = load_generate_entity_id()
    assert gen("SL_SPOT", "HUB1", "SPOT1", "remote") == (
        "remote.sl_spot_hub1_spot1_remote"
    )
    assert gen("SL_P_IR", "HUB1", "IR1", "remote") == (
        "remote.sl_p_ir_hub1_ir1_remote"
    )


def test_spot_ac_climate_device():
    gen = load_generate_entity_id()
    assert gen("SL_SPOT", "HUB1", "SPOT1", "climate_ac") == (
        "climate.sl_spot_hub1_spot1_climate_ac"
    )
