from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import PERCENTAGE, UnitOfTemperature

from tests.lifesmart_entity_helpers import make_binary_sensor, make_sensor


def test_defed_siren_binary_state_and_tamper():
    siren = make_binary_sensor("SL_DF_SR", "SR", {"type": 1, "val": 0})
    assert siren.is_on is True
    assert siren.device_class == BinarySensorDeviceClass.SOUND

    tamper = make_binary_sensor("SL_DF_SR", "TR", {"type": 0, "val": 0})
    assert tamper.is_on is False
    assert tamper.device_class == BinarySensorDeviceClass.TAMPER
    assert (
        tamper._state_from_data({"devtype": "SL_DF_SR", "idx": "TR", "type": 1})
        is True
    )


def test_defed_keyfob_buttons_are_press_binary_sensors():
    button = make_binary_sensor("SL_DF_BB", "eB3", {"type": 1, "val": 0})
    assert button.is_on is True
    assert button.device_class is None

    assert (
        button._state_from_data({"devtype": "SL_DF_BB", "idx": "eB3", "type": 0})
        is False
    )


def test_defed_siren_temperature_and_battery_sensors():
    temperature = make_sensor("SL_DF_SR", "T", {"val": 236})
    assert temperature.state == 23.6
    assert temperature.device_class == SensorDeviceClass.TEMPERATURE
    assert temperature.unit_of_measurement == UnitOfTemperature.CELSIUS

    battery = make_sensor("SL_DF_SR", "V", {"val": 3000, "v": 87})
    assert battery.state == 87
    assert battery.device_class == SensorDeviceClass.BATTERY
    assert battery.unit_of_measurement == PERCENTAGE
    assert battery.extra_state_attributes == {"raw": 3000}


def test_defed_keyfob_battery_sensor():
    battery = make_sensor("SL_DF_BB", "V", {"val": 3000, "v": 92})
    assert battery.state == 92
    assert battery.device_class == SensorDeviceClass.BATTERY
    assert battery.unit_of_measurement == PERCENTAGE
