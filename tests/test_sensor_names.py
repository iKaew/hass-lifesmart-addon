"""Translated sensor names without changing channel identities or readings."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import homeassistant
import pytest

from custom_components.lifesmart.binary_sensor import LifeSmartBinarySensor
from custom_components.lifesmart.entity_names import resolve_sensor_channel_name
from custom_components.lifesmart.sensor import LifeSmartSensor

ROOT = Path(__file__).resolve().parents[1] / "custom_components/lifesmart"
HA_ROOT = Path(homeassistant.__file__).parent


def make_entity(domain, model, channel, name):
    data = {"name": name, "type": 128, "val": 0, "v": 0}
    raw = {
        "name": "Utility sensor", "devtype": model, "agt": "HUB1",
        "me": "DEV1", "ver": "1.0", "data": {channel: data},
    }
    cls = LifeSmartSensor if domain == "sensor" else LifeSmartBinarySensor
    entity = cls(None, raw, channel, data, None)
    entity.platform_data = SimpleNamespace(platform_name="lifesmart", domain=domain)
    return entity


def translated_name(entity, domain, language):
    translations = json.loads((ROOT / "translations" / f"{language}.json").read_text())
    flat = {
        f"component.lifesmart.entity.{domain}.{key}.name": value["name"]
        for key, value in translations["entity"].get(domain, {}).items()
        if "name" in value
    }
    # Use HA's English source as the baseline; translated core resources may
    # not be bundled in the test environment. Integration translations are
    # checked independently for every supported language above.
    core = json.loads((HA_ROOT / "components" / domain / "strings.json").read_text())
    class_name = core["entity_component"].get(entity.device_class, {}).get("name")
    return entity._name_internal(class_name, flat)


@pytest.mark.parametrize("language", ["en", "es", "th", "zh-Hans"])
@pytest.mark.parametrize(
    ("domain", "model", "channel", "expected"),
    [
        ("sensor", "SL_SC_BE", "T", "Temperature"),
        ("sensor", "SL_SC_BE", "H", "Humidity"),
        ("sensor", "SL_SC_BE", "Z", "Illuminance"),
        ("sensor", "SL_SC_BE", "V", "Battery"),
        ("sensor", "SL_SC_WA", "V", "Battery"),
        ("binary_sensor", "SL_SC_WA", "WA", "Moisture"),
        ("sensor", "SL_SC_CP", "P1", "Gas concentration"),
        ("sensor", "SL_SC_CP", "P2", "Alarm threshold"),
        ("sensor", "SL_SC_CH", "P1", "Formaldehyde concentration"),
        ("sensor", "SL_SC_CH", "P2", "Alarm threshold"),
        ("binary_sensor", "SL_SC_CP", "P3", "Alarm sound"),
        ("binary_sensor", "SL_SC_CH", "P3", "Alarm sound"),
    ],
)
def test_default_sensor_names_and_identities(language, domain, model, channel, expected):
    entity = make_entity(domain, model, channel, "{$EPN} {" + channel + "}")
    name = translated_name(entity, domain, language)
    assert isinstance(name, str) and name
    assert "{" not in name
    assert entity.has_entity_name is True
    assert entity.unique_id == f"{domain}.{model.lower()}_hub1_dev1_{channel.lower()}"
    assert entity.entity_id is None
    assert entity.device_info["name"] == "Utility sensor"
    assert entity.entity_category is None
    if language == "en":
        assert name == expected


@pytest.mark.parametrize("name", [None, "", "none", "T", "{$EPN}", "{$EPN} T", "{$EPN} {T}"])
def test_missing_or_generic_name_uses_function(name):
    entity = make_entity("sensor", "SL_SC_BE", "T", name)
    assert translated_name(entity, "sensor", "en") == "Temperature"


@pytest.mark.parametrize("domain,model,channel", [
    ("sensor", "SL_SC_BE", "T"),
    ("sensor", "SL_SC_CP", "P1"),
    ("sensor", "SL_SC_CP", "P2"),
    ("binary_sensor", "SL_SC_WA", "WA"),
    ("binary_sensor", "SL_SC_CP", "P3"),
])
@pytest.mark.parametrize("name,expected", [
    ("Desk reading", "Desk reading"),
    ("{$EPN} Desk reading", "Desk reading"),
    ("Reading {custom}", "Reading {custom}"),
])
def test_custom_channel_names_take_precedence(domain, model, channel, name, expected):
    entity = make_entity(domain, model, channel, name)
    assert translated_name(entity, domain, "en") == expected
    assert entity.translation_key is None


def test_unknown_templates_keep_channel_fallback():
    assert resolve_sensor_channel_name("{$EPN} {unknown}", "T", "SL_SC_BE") == "T"
    assert resolve_sensor_channel_name("{$EPN} {H}", "T", "SL_SC_BE") == "T"
    entity = make_entity("sensor", "SL_SC_BE", "T", "{$EPN} {unknown}")
    assert translated_name(entity, "sensor", "en") == "T"


def test_sensor_without_device_class_keeps_distinguishable_channel():
    entity = make_entity("sensor", "SL_SC_MHW", "P3", "{$EPN} {P3}")
    assert translated_name(entity, "sensor", "en") == "P3"


@pytest.mark.parametrize("name_format", [
    None, "", "none", "{channel}", "{{$EPN}}", "{{$EPN}} {channel}",
    "{{$EPN}} {{{channel}}}",
])
@pytest.mark.parametrize("domain,model,channels", [
    ("binary_sensor", "SL_P", ("P5", "P6", "P7")),
    ("binary_sensor", "SL_JEMA", ("P5", "P6", "P7")),
    ("sensor", "V_485_P", ("EE1", "EE2")),
    ("sensor", "V_485_P", ("CH2OPPM", "NH3PPM")),
    ("sensor", "V_485_P", ("T", "H")),
    ("sensor", "SL_SC_THL", ("T", "H")),
])
def test_unmapped_channels_keep_distinct_names(domain, model, channels, name_format):
    entities = [
        make_entity(
            domain, model, channel,
            name_format.format(channel=channel) if name_format is not None else None,
        )
        for channel in channels
    ]
    assert [translated_name(entity, domain, "en") for entity in entities] == list(channels)
    assert len({entity.unique_id for entity in entities}) == len(channels)
    for entity, channel in zip(entities, channels, strict=True):
        assert entity.unique_id == f"{domain}.{model.lower()}_hub1_dev1_{channel.lower()}"
        assert entity.translation_key is None


@pytest.mark.parametrize("model,channel", [
    ("UNKNOWN_MODEL", "T"),
    ("UNKNOWN_MODEL", "P5"),
    ("SL_SC_BE", "P1"),
    ("SL_SC_WA", "G"),
])
@pytest.mark.parametrize("name_format", [
    None, "", "none", "{channel}", "{{$EPN}}", "{{$EPN}} {channel}",
    "{{$EPN}} {{{channel}}}",
])
def test_unknown_model_or_unmapped_port_keeps_channel(model, channel, name_format):
    name = name_format.format(channel=channel) if name_format is not None else None
    assert resolve_sensor_channel_name(name, channel, model) == channel


@pytest.mark.parametrize("domain,model,channel", [
    ("binary_sensor", "SL_P", "P5"),
    ("binary_sensor", "SL_JEMA", "P6"),
    ("sensor", "V_485_P", "EE2"),
    ("sensor", "V_485_P", "NH3PPM"),
])
@pytest.mark.parametrize("name,expected", [
    ("Utility input", "Utility input"),
    ("{$EPN} Utility input", "Utility input"),
    ("{$EPN} {unknown}", None),
])
def test_unmapped_channels_preserve_custom_names(domain, model, channel, name, expected):
    entity = make_entity(domain, model, channel, name)
    assert translated_name(entity, domain, "en") == (expected or channel)
    assert entity.translation_key is None


def test_names_do_not_change_reading_or_alarm_sound_semantics():
    sensor = make_entity("sensor", "SL_SC_BE", "T", "{$EPN} {T}")
    sensor.schedule_update_ha_state = lambda: None
    asyncio.run(sensor._update_value({"val": 235, "v": 23.5, "type": 0}))
    assert sensor.state == 23.5
    assert translated_name(sensor, "sensor", "en") == "Temperature"

    sounder = make_entity("binary_sensor", "SL_SC_CP", "P3", "P3")
    sounder.schedule_update_ha_state = lambda: None
    asyncio.run(sounder._update_state({"devtype": "SL_SC_CP", "idx": "P3", "val": 0, "type": 129}))
    assert sounder.is_on is True
    assert translated_name(sounder, "binary_sensor", "en") == "Alarm sound"
    asyncio.run(sounder._update_state({"devtype": "SL_SC_CP", "idx": "P3", "val": 1, "type": 128}))
    assert sounder.is_on is False
