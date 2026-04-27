"""lifesmart by @ikaew."""

from homeassistant.components import climate
from homeassistant.const import Platform

CONF_LIFESMART_APPKEY = "appkey"
CONF_LIFESMART_APPTOKEN = "apptoken"
CONF_LIFESMART_USERTOKEN = "usertoken"
CONF_LIFESMART_USERID = "userid"
CONF_LIFESMART_USERPASSWORD = "userpassword"
CONF_EXCLUDE_ITEMS = "exclude"
CONF_EXCLUDE_AGTS = "exclude_agt"
CONF_AI_INCLUDE_AGTS = "ai_include_agt"
CONF_AI_INCLUDE_ITEMS = "ai_include_me"
CONF_AC_CONFIG = "ac_config"
IR_CATEGORY_AC = "ac"

CON_AI_TYPE_SCENE = "scene"
CON_AI_TYPE_AIB = "aib"
CON_AI_TYPE_GROUP = "grouphw"
CON_AI_TYPES = [
    CON_AI_TYPE_SCENE,
    CON_AI_TYPE_AIB,
    CON_AI_TYPE_GROUP,
]
AI_TYPES = ["ai"]
SUPPORTED_SWTICH_TYPES = [
    "OD_WE_OT1",
    "SL_MC_ND1",
    "SL_MC_ND2",
    "SL_MC_ND3",
    "SL_NATURE",
    "SL_OL",
    "SL_OL_3C",
    "SL_OL_DE",
    "SL_OL_UK",
    "SL_OL_UL",
    "SL_OL_W",
    "SL_P_SW",
    "SL_S",
    "SL_SF_IF1",
    "SL_SF_IF2",
    "SL_SF_IF3",
    "SL_SF_RC",
    "SL_SPWM",
    "SL_SW_CP1",
    "SL_SW_CP2",
    "SL_SW_CP3",
    "SL_SW_DM1",
    "SL_SW_FE1",
    "SL_SW_FE2",
    "SL_SW_IF1",
    "SL_SW_IF2",
    "SL_SW_IF3",
    "SL_SW_MJ1",
    "SL_SW_MJ2",
    "SL_SW_MJ3",
    "SL_SW_ND1",
    "SL_SW_ND2",
    "SL_SW_ND3",
    "SL_SW_RC",
    "SL_SW_RC1",
    "SL_SW_RC2",
    "SL_SW_RC3",
    "SL_SW_NS1",
    "SL_SW_NS2",
    "SL_SW_NS3",
    "V_IND_S",
]

SUPPORTED_SUB_SWITCH_TYPES = [
    "L1",
    "L2",
    "L3",
    "P1",
    "P2",
    "P3",
]

SUPPORTED_SUB_BINARY_SENSORS = [
    "M",
    "G",
    "B",
    "AXS",
    "WA",
    "P1",
    "P5",
    "P6",
    "P7",
]

LIGHT_SWITCH_TYPES = [
    "SL_OL_W",
    "SL_SW_IF1",
    "SL_SW_IF2",
    "SL_SW_IF3",
    "SL_CT_RGBW",
]
LIGHT_DIMMER_TYPES = [
    "SL_LI_WW",
]

QUANTUM_TYPES = [
    "OD_WE_QUAN",
]
MOTION_SENSOR_TYPES = ["SL_SC_MHW", "SL_SC_BM", "SL_SC_CM"]
RADAR_MOTION_SENSOR_TYPES = ["SL_P_RM"]
SMOKE_SENSOR_TYPES = ["SL_P_A"]
WATER_LEAK_SENSOR_TYPES = ["SL_SC_WA"]
CO2_SENSOR_TYPES = ["SL_SC_CA"]
ENV_SENSOR_TYPES = ["SL_SC_THL", "SL_SC_BE"]
TVOC_CO2_SENSOR_TYPES = ["SL_SC_CQ"]
DEFED_DOOR_SENSOR_TYPES = ["SL_DF_GG"]
DEFED_MOTION_SENSOR_TYPES = ["SL_DF_MM"]
DEFED_SIREN_TYPES = ["SL_DF_SR"]
DEFED_KEYFOB_TYPES = ["SL_DF_BB"]
DEFED_SENSOR_TYPES = (
    DEFED_DOOR_SENSOR_TYPES
    + DEFED_MOTION_SENSOR_TYPES
    + DEFED_SIREN_TYPES
    + DEFED_KEYFOB_TYPES
)
NOISE_SENSOR_TYPES = ["SL_SC_CN"]
SMART_ALARM_TYPES = ["SL_ALM"]
AIR_PURIFIER_TYPES = ["OD_MFRESH_M8088"]
GARAGE_DOOR_TYPES = ["SL_ETDOOR"]
HA_CONTROLLER_TYPES = ["SL_JEMA"]
DLT_METER_TYPES = ["V_DLT_645_P", "V_DLT645_P"]
MODBUS_CONTROLLER_TYPES = ["V_485_P"]
SPOT_LIGHT_TYPES = ["MSL_IRCTL", "OD_WE_IRCTL", "SL_SPOT"]
SPOT_IR_TYPES = ["SL_P_IR", "SL_P_IR_V2"]
SPOT_TYPES = [*SPOT_LIGHT_TYPES, *SPOT_IR_TYPES]
BINARY_SENSOR_TYPES = [
    "SL_SC_G",
    "SL_SC_BG",
    *MOTION_SENSOR_TYPES,
    *SMOKE_SENSOR_TYPES,
    "SL_P",
]
COVER_TYPES = [
    "SL_DOOYA",  # Curtain (DuYa)
    "SL_DOOYA_V2",  # Quick Link Curtain Motor
    "SL_DOOYA_V3",  # Tubular Motor
    "SL_DOOYA_V4",  # Tubular Motor (lithium battery)
    "SL_SW_WIN",  # Curtain controller
    "SL_CN_IF",  # BLEND curtain controller
    "SL_CN_FE",  # Gezhi/Sennathree-keycurtain
    "SL_P_V2",  # MINS curtain motor controller
    *GARAGE_DOOR_TYPES,
]
GAS_SENSOR_TYPES = ["SL_SC_CH", "SL_SC_CP"]
ELECTRICITY_METER_TYPES = ["ELIQ_EM"]
EV_SENSOR_TYPES = ENV_SENSOR_TYPES + TVOC_CO2_SENSOR_TYPES
OT_SENSOR_TYPES = ["SL_SC_MHW", "SL_SC_BM", "SL_SC_G", "SL_SC_BG"]
LOCK_TYPES = [
    "SL_LK_LS",
    "SL_LK_GTM",
    "SL_LK_AG",
    "SL_LK_SG",
    "SL_LK_YL",
    "SL_LK_TY",
    "SL_LK_DJ",
]
GUARD_SENSOR_TYPES = ["SL_SC_G", "SL_SC_BG"]
DEVICE_WITHOUT_IDXNAME = [
    "SL_NATURE",
    "SL_SW_ND1",
    "SL_SW_ND2",
    "SL_SW_ND3",
    "SL_SW_MJ1",
    "SL_SW_MJ2",
    "SL_SW_MJ3",
]
GENERIC_CONTROLLER_TYPES = ["SL_P", *HA_CONTROLLER_TYPES]
GENERIC_CONTROLLER_SWITCH_PORTS = ["P2", "P3", "P4"]
HA_CONTROLLER_SWITCH_PORTS = [*GENERIC_CONTROLLER_SWITCH_PORTS, "P8", "P9", "P10"]
GENERIC_CONTROLLER_BINARY_PORTS = ["P5", "P6", "P7"]
SMART_PLUG_TYPES = ["SL_OE_DE"]
NATURE_TYPES = ["SL_NATURE"]
NATURE_SWITCH_PORTS = ["P1", "P2", "P3"]
NATURE_CLIMATE_KEY = "climate"

LIFESMART_HVAC_STATE_LIST = [
    climate.const.HVACMode.OFF,
    climate.const.HVACMode.AUTO,
    climate.const.HVACMode.FAN_ONLY,
    climate.const.HVACMode.COOL,
    climate.const.HVACMode.HEAT,
    climate.const.HVACMode.DRY,
]

SUPPORTED_PLATFORMS = [
    Platform.SWITCH,
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.COVER,
    Platform.LIGHT,
    Platform.REMOTE,
    Platform.CLIMATE,
]
AIR_CONDITIONER_TYPES = [
    "V_AIR_P",
    "V_SZJSXR_P",
    "V_T8600_P",
]
THERMOSTAT_TYPES = ["SL_CP_DN"]
CLIMATE_TYPES = AIR_CONDITIONER_TYPES + THERMOSTAT_TYPES


ENTITYID = "entity_id"
DOMAIN = "lifesmart"

MANUFACTURER = "LifeSmart"

DEVICE_ID_KEY = "me"
SUBDEVICE_INDEX_KEY = "idx"
DEVICE_TYPE_KEY = "devtype"
HUB_ID_KEY = "agt"
DEVICE_NAME_KEY = "name"
DEVICE_DATA_KEY = "data"
DEVICE_VERSION_KEY = "ver"

LIFESMART_STATE_MANAGER = "lifesmart_wss"
UPDATE_LISTENER = "update_listener"

LIFESMART_SIGNAL_UPDATE_ENTITY = "lifesmart_updated"

LIFESMART_REGION_OPTIONS = {
    "select": {
        "options": ["cn0", "cn1", "cn2", "us", "eur", "jp", "apz"],
    }
}

DIGITAL_DOORLOCK_LOCK_EVENT_KEY = "EVTLO"
DIGITAL_DOORLOCK_ALARM_EVENT_KEY = "ALM"
DIGITAL_DOORLOCK_BATTERY_EVENT_KEY = "BAT"
DIGITAL_DOORLOCK_DOORBELL_EVENT_KEY = "EVTBELL"
DIGITAL_DOORLOCK_OPERATION_EVENT_KEY = "EVTOP"
DIGITAL_DOORLOCK_HISTORY_LOCK_EVENT_KEY = "HISLK"


def is_nature_thermostat(device):
    """Return true for SL_NATURE thermostat variants."""
    if device.get(DEVICE_TYPE_KEY) not in NATURE_TYPES:
        return False

    data = device.get(DEVICE_DATA_KEY, {})
    device_type_value = data.get("P5", {}).get("val", 0) & 0xFF
    if device_type_value in (3, 6):
        return True

    return all(idx in data for idx in ("P1", "P4", "P6", "P7", "P8"))


def is_nature_switch(device):
    """Return true for SL_NATURE switch-board variants."""
    if device.get(DEVICE_TYPE_KEY) not in NATURE_TYPES:
        return False

    data = device.get(DEVICE_DATA_KEY, {})
    device_type_value = data.get("P5", {}).get("val")
    if device_type_value is None:
        return True
    return device_type_value & 0xFF == 1
