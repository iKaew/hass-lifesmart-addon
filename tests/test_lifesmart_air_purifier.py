from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import (
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    PERCENTAGE,
    UnitOfTemperature,
    UnitOfTime,
)

from tests.lifesmart_entity_helpers import make_sensor, make_switch


def test_air_purifier_power_switch_state():
    power = make_switch("OD_MFRESH_M8088", "O", {"type": 1, "val": 1})
    assert power.is_on is True

    off_power = make_switch("OD_MFRESH_M8088", "O", {"type": 0, "val": 0})
    assert off_power.is_on is False


def test_air_purifier_mode_sensor():
    mode = make_sensor("OD_MFRESH_M8088", "RM", {"val": 4})
    assert mode.state == "max"
    assert mode.device_class == SensorDeviceClass.ENUM
    assert mode.unit_of_measurement is None
    assert mode.options == ["auto", "fan_1", "fan_2", "fan_3", "max", "sleep"]
    assert mode.extra_state_attributes == {"raw": 4}


def test_air_purifier_environment_sensors():
    temperature = make_sensor("OD_MFRESH_M8088", "T", {"val": 236})
    assert temperature.state == 23.6
    assert temperature.device_class == SensorDeviceClass.TEMPERATURE
    assert temperature.unit_of_measurement == UnitOfTemperature.CELSIUS

    humidity = make_sensor("OD_MFRESH_M8088", "H", {"val": 523})
    assert humidity.state == 52.3
    assert humidity.device_class == SensorDeviceClass.HUMIDITY
    assert humidity.unit_of_measurement == PERCENTAGE

    pm25 = make_sensor("OD_MFRESH_M8088", "PM", {"val": 18})
    assert pm25.state == 18
    assert pm25.device_class == SensorDeviceClass.PM25
    assert pm25.unit_of_measurement == CONCENTRATION_MICROGRAMS_PER_CUBIC_METER


def test_air_purifier_filter_life_and_uv_sensors():
    filter_life = make_sensor("OD_MFRESH_M8088", "FL", {"val": 3200})
    assert filter_life.state == 3200
    assert filter_life.device_class == SensorDeviceClass.DURATION
    assert filter_life.unit_of_measurement == UnitOfTime.HOURS

    uv = make_sensor("OD_MFRESH_M8088", "UV", {"val": 6})
    assert uv.state == 6
    assert uv.device_class is None
    assert uv.unit_of_measurement == "None"
    assert uv.extra_state_attributes == {"raw": 6}
