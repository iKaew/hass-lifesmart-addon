"""Names and identities for LifeSmart outlet and indicator channels."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from homeassistant.helpers.entity import EntityCategory

from custom_components.lifesmart.entity_names import resolve_channel_name
from custom_components.lifesmart.light import LifeSmartLight
from custom_components.lifesmart.switch import LifeSmartSwitch


@pytest.mark.parametrize(
    ("name", "port", "expected"),
    [
        ("{$EPN}", "O", None),
        ("{$EPN}", "P1", "P1"),
        ("{$EPN}", "P2", "P2"),
        ("{$EPN} 2", "L2", "2"),
        ("{$EPN} Desk", "L1", "Desk"),
        ("{$EPN} {unknown}", "L1", "L1"),
        ("Study ceiling light", "P1", "Study ceiling light"),
        ("Reading {custom}", "P8", "Reading {custom}"),
        ("", "O", ""),
        (None, "O", None),
    ],
)
def test_channel_name_resolution(name, port, expected):
    assert resolve_channel_name(name, port) == expected


def make_device(model, data):
    return {"name": "Outlet", "devtype": model, "agt": "HUB1", "me": "DEV1", "ver": "1.0", "data": data}


def test_outlet_name_uses_device_name_and_preserves_unique_id():
    data = {"O": {"name": "{$EPN}", "type": 128, "val": 0}}
    entity = LifeSmartSwitch(None, make_device("SL_OL_3C", data), "O", data["O"], None)
    assert entity.has_entity_name is True
    assert entity.name is None
    assert entity.device_info["name"] == "Outlet"
    assert entity.unique_id == "switch.sl_ol_3c_hub1_dev1_o"
    assert entity.entity_id is None  # The entity registry still owns the existing ID.
    assert entity.entity_category is None


@pytest.mark.parametrize("language", ["en", "es", "th", "zh-Hans"])
def test_indicator_names_are_translated_distinct_and_keep_identities(language):
    path = Path(__file__).resolve().parents[1] / "custom_components/lifesmart/translations" / f"{language}.json"
    translations = json.loads(path.read_text())["entity"]["light"]
    flat = {f"component.lifesmart.entity.light.{key}.name": value["name"] for key, value in translations.items()}
    names = []
    for port in ("bright", "dark", "bright1", "dark1", "bright2", "dark2", "bright3", "dark3"):
        token = "bright" if port.startswith("bright") else "dark"
        number = port[-1] if port[-1].isdigit() else ""
        data = {port: {"name": "{$EPN} {" + token + "}" + number, "type": 211, "val": 50}}
        entity = LifeSmartLight(None, make_device("SL_OL_3C", data), port, data[port], None)
        entity.platform_data = SimpleNamespace(platform_name="lifesmart", domain="light")
        name = entity._name_internal(None, flat)
        assert isinstance(name, str)
        assert "{" not in name
        assert entity.entity_category is EntityCategory.CONFIG
        assert entity.unique_id == f"switch.sl_ol_3c_hub1_dev1_{port}"
        assert entity.entity_id is None
        if number:
            assert number in name
        names.append(name)
    assert len(set(names)) == 8
    if language == "en":
        assert names == [
            "Indicator when on",
            "Indicator when off",
            "Indicator when on (channel 1)",
            "Indicator when off (channel 1)",
            "Indicator when on (channel 2)",
            "Indicator when off (channel 2)",
            "Indicator when on (channel 3)",
            "Indicator when off (channel 3)",
        ]


@pytest.mark.parametrize("name", ["Desk indicator", "{$EPN} Desk indicator"])
def test_explicit_indicator_name_is_preserved(name):
    data = {"bright": {"name": name, "type": 211, "val": 50}}
    entity = LifeSmartLight(None, make_device("SL_OL_3C", data), "bright", data["bright"], None)
    assert entity.name == "Desk indicator"
    assert entity.entity_category is EntityCategory.CONFIG


@pytest.mark.parametrize("name", [None, "", "bright", "Outlet"])
def test_missing_or_generic_indicator_name_gets_functional_label(name):
    data = {"bright": {"name": name, "type": 211, "val": 50}}
    entity = LifeSmartLight(None, make_device("SL_OL_3C", data), "bright", data["bright"], None)
    assert entity.translation_key == "indicator_on"


def test_main_light_keeps_existing_category_and_identity():
    data = {"RGBW": {"type": 129, "val": 0x00112233}}
    entity = LifeSmartLight(None, make_device("SL_CT_RGBW", data), "RGBW", data["RGBW"], None)
    assert entity.entity_category is None
    assert entity.translation_key is None
    assert entity.unique_id == "light.sl_ct_rgbw_hub1_dev1_rgbw"
