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
    "O",
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
    "OD_WE_QUAN",
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

LIFESMART_REGION_DIRECT_OPTIONS = {
    "": "Global/default",
    "cn0": "China old server",
    "cn1": "China special server",
    "cn2": "China new server",
    "us": "America server",
    "eur": "Europe server",
    "jp": "Japan server",
    "apz": "Asia Pacific server",
}

LIFESMART_COUNTRY_REGION_MAP = {
    "country:ae": "us",
    "country:ag": "us",
    "country:am": "eur",
    "country:apz": "apz",
    "country:ar": "us",
    "country:at": "eur",
    "country:au": "us",
    "country:bb": "us",
    "country:bd": "apz",
    "country:be": "eur",
    "country:bg": "eur",
    "country:bh": "us",
    "country:bn": "apz",
    "country:bo": "us",
    "country:br": "us",
    "country:bs": "us",
    "country:by": "eur",
    "country:bz": "us",
    "country:ca": "us",
    "country:ch": "eur",
    "country:cl": "us",
    "country:cn": "cn0",
    "country:cn1": "cn1",
    "country:cn2": "cn2",
    "country:co": "us",
    "country:cr": "us",
    "country:cy": "eur",
    "country:cz": "eur",
    "country:de": "eur",
    "country:dk": "eur",
    "country:dm": "us",
    "country:do": "us",
    "country:dz": "us",
    "country:ec": "us",
    "country:ee": "eur",
    "country:eg": "us",
    "country:es": "eur",
    "country:et": "us",
    "country:fi": "eur",
    "country:fr": "eur",
    "country:gb": "eur",
    "country:gd": "us",
    "country:gh": "us",
    "country:gr": "eur",
    "country:gt": "us",
    "country:gy": "us",
    "country:hk": "us",
    "country:hn": "us",
    "country:hr": "eur",
    "country:hu": "eur",
    "country:id": "us",
    "country:ie": "eur",
    "country:il": "us",
    "country:in": "us",
    "country:iq": "apz",
    "country:ir": "us",
    "country:is": "eur",
    "country:it": "eur",
    "country:jm": "us",
    "country:jo": "us",
    "country:jp": "us",
    "country:ke": "us",
    "country:kh": "us",
    "country:kr": "us",
    "country:kw": "us",
    "country:kz": "apz",
    "country:lc": "us",
    "country:li": "eur",
    "country:lk": "apz",
    "country:lt": "eur",
    "country:lu": "eur",
    "country:lv": "eur",
    "country:ma": "us",
    "country:md": "eur",
    "country:me": "eur",
    "country:mk": "eur",
    "country:mm": "apz",
    "country:mn": "apz",
    "country:mo": "us",
    "country:mt": "eur",
    "country:mu": "us",
    "country:mx": "us",
    "country:my": "apz",
    "country:ng": "us",
    "country:ni": "us",
    "country:nl": "eur",
    "country:no": "eur",
    "country:np": "apz",
    "country:nz": "us",
    "country:om": "us",
    "country:pa": "us",
    "country:pe": "us",
    "country:ph": "apz",
    "country:pk": "apz",
    "country:pl": "eur",
    "country:pt": "eur",
    "country:py": "us",
    "country:qa": "us",
    "country:ro": "eur",
    "country:rs": "eur",
    "country:ru": "eur",
    "country:sa": "us",
    "country:se": "eur",
    "country:sg": "apz",
    "country:si": "eur",
    "country:sk": "eur",
    "country:sr": "us",
    "country:sv": "us",
    "country:th": "apz",
    "country:tr": "eur",
    "country:tt": "us",
    "country:tw": "us",
    "country:ua": "eur",
    "country:us": "us",
    "country:uy": "us",
    "country:ve": "us",
    "country:vn": "apz",
    "country:za": "us",
}

LIFESMART_COUNTRY_LABELS = {
    "country:ae": "United Arab Emirates",
    "country:ag": "Antigua and Barbuda",
    "country:am": "Armenia",
    "country:apz": "Asia Pacific",
    "country:ar": "Argentina",
    "country:at": "Austria",
    "country:au": "Australia",
    "country:bb": "Barbados",
    "country:bd": "Bangladesh",
    "country:be": "Belgium",
    "country:bg": "Bulgaria",
    "country:bh": "Bahrain",
    "country:bn": "Brunei",
    "country:bo": "Bolivia",
    "country:br": "Brazil",
    "country:bs": "Bahamas",
    "country:by": "Belarus",
    "country:bz": "Belize",
    "country:ca": "Canada",
    "country:ch": "Switzerland",
    "country:cl": "Chile",
    "country:cn": "China old",
    "country:cn1": "Hotel and corporate users",
    "country:cn2": "China new",
    "country:co": "Colombia",
    "country:cr": "Costa Rica",
    "country:cy": "Cyprus",
    "country:cz": "Czech Republic",
    "country:de": "Germany",
    "country:dk": "Denmark",
    "country:dm": "Dominica",
    "country:do": "Dominican Republic",
    "country:dz": "Algeria",
    "country:ec": "Ecuador",
    "country:ee": "Estonia",
    "country:eg": "Egypt",
    "country:es": "Spain",
    "country:et": "Ethiopia",
    "country:fi": "Finland",
    "country:fr": "France",
    "country:gb": "United Kingdom",
    "country:gd": "Grenada",
    "country:gh": "Ghana",
    "country:gr": "Greece",
    "country:gt": "Guatemala",
    "country:gy": "Guyana",
    "country:hk": "China, Hong Kong",
    "country:hn": "Honduras",
    "country:hr": "Croatia",
    "country:hu": "Hungary",
    "country:id": "Indonesia",
    "country:ie": "Ireland",
    "country:il": "Israel",
    "country:in": "India",
    "country:iq": "Republic of Iraq",
    "country:ir": "Iran",
    "country:is": "Iceland",
    "country:it": "Italy",
    "country:jm": "Jamaica",
    "country:jo": "Jordan",
    "country:jp": "Japan",
    "country:ke": "Kenya",
    "country:kh": "Cambodia",
    "country:kr": "Korea",
    "country:kw": "Kuwait",
    "country:kz": "Kazakhstan",
    "country:lc": "St. Lucia",
    "country:li": "Liechtenstein",
    "country:lk": "Sri Lanka",
    "country:lt": "Lithuania",
    "country:lu": "Luxembourg",
    "country:lv": "Latvia",
    "country:ma": "Morocco",
    "country:md": "Moldova, Republic of",
    "country:me": "Montenegro",
    "country:mk": "Macedonia",
    "country:mm": "Myanmar",
    "country:mn": "Mongolia",
    "country:mo": "China, Macao",
    "country:mt": "Malta",
    "country:mu": "Mauritius",
    "country:mx": "Mexico",
    "country:my": "Malaysia",
    "country:ng": "Federal Republic of Nigeria",
    "country:ni": "Nicaragua",
    "country:nl": "Netherlands",
    "country:no": "Norway",
    "country:np": "Nepal",
    "country:nz": "New Zealand",
    "country:om": "Oman",
    "country:pa": "Panama",
    "country:pe": "Peru",
    "country:ph": "Philippines",
    "country:pk": "Pakistan",
    "country:pl": "Poland",
    "country:pt": "Portugal",
    "country:py": "Paraguay",
    "country:qa": "Qatar",
    "country:ro": "Romania",
    "country:rs": "Serbia",
    "country:ru": "Russia",
    "country:sa": "Saudi Arabia",
    "country:se": "Sweden",
    "country:sg": "Singapore",
    "country:si": "Slovenia",
    "country:sk": "Slovakia",
    "country:sr": "Suriname",
    "country:sv": "El Salvador",
    "country:th": "Thailand",
    "country:tr": "Turkey",
    "country:tt": "Trinidad and Tobago",
    "country:tw": "China, Taiwan",
    "country:ua": "Ukraine",
    "country:us": "United States of America",
    "country:uy": "Uruguay",
    "country:ve": "Venezuela",
    "country:vn": "Vietnam",
    "country:za": "South Africa",
}


def normalize_lifesmart_region(region):
    """Resolve country selections and legacy service codes to API region values."""
    if region is None:
        return ""

    region = str(region)
    service_code_regions = {
        "GS": "",
        "CN0": "cn0",
        "VIP1": "cn1",
        "CN2": "cn2",
        "AME": "us",
        "EUR": "eur",
        "JAP": "jp",
        "APZ": "apz",
    }
    if region in LIFESMART_COUNTRY_REGION_MAP:
        return LIFESMART_COUNTRY_REGION_MAP[region]
    return service_code_regions.get(region.upper(), region)


def _lifesmart_region_options():
    """Return selectable countries plus legacy direct server choices."""
    direct_options = [
        {"value": value, "label": f"Server: {label}"}
        for value, label in LIFESMART_REGION_DIRECT_OPTIONS.items()
    ]
    country_options = [
        {
            "value": value,
            "label": f"{label} ({normalize_lifesmart_region(value) or 'default'})",
        }
        for value, label in sorted(
            LIFESMART_COUNTRY_LABELS.items(), key=lambda item: item[1]
        )
    ]
    return direct_options + country_options


LIFESMART_REGION_OPTIONS = {
    "select": {
        "options": _lifesmart_region_options(),
        "mode": "dropdown",
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
