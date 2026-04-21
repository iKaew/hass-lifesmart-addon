from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import (
    CONCENTRATION_MILLIGRAMS_PER_CUBIC_METER,
    CONCENTRATION_PARTS_PER_MILLION,
    LIGHT_LUX,
    PERCENTAGE,
    UnitOfElectricPotential,
    UnitOfTemperature,
)

from tests.lifesmart_entity_helpers import make_sensor


def test_env_sensor_temperature_humidity_illuminance_and_battery():
    temperature = make_sensor("SL_SC_THL", "T", {"val": 236})
    assert temperature.state == 23.6
    assert temperature.device_class == SensorDeviceClass.TEMPERATURE
    assert temperature.unit_of_measurement == UnitOfTemperature.CELSIUS

    humidity = make_sensor("SL_SC_BE", "H", {"val": 523})
    assert humidity.state == 52.3
    assert humidity.device_class == SensorDeviceClass.HUMIDITY
    assert humidity.unit_of_measurement == PERCENTAGE

    illuminance = make_sensor("SL_SC_THL", "Z", {"val": 860})
    assert illuminance.state == 860
    assert illuminance.device_class == SensorDeviceClass.ILLUMINANCE
    assert illuminance.unit_of_measurement == LIGHT_LUX

    battery = make_sensor("SL_SC_BE", "V", {"val": 3000, "v": 78})
    assert battery.state == 78
    assert battery.device_class == SensorDeviceClass.BATTERY
    assert battery.unit_of_measurement == PERCENTAGE
    assert battery.extra_state_attributes == {"raw": 3000}


def test_tvoc_co2_sensor_values_and_classes():
    temperature = make_sensor("SL_SC_CQ", "P1", {"val": 241})
    assert temperature.state == 24.1
    assert temperature.device_class == SensorDeviceClass.TEMPERATURE
    assert temperature.unit_of_measurement == UnitOfTemperature.CELSIUS

    humidity = make_sensor("SL_SC_CQ", "P2", {"val": 486})
    assert humidity.state == 48.6
    assert humidity.device_class == SensorDeviceClass.HUMIDITY
    assert humidity.unit_of_measurement == PERCENTAGE

    co2 = make_sensor("SL_SC_CQ", "P3", {"val": 615})
    assert co2.state == 615
    assert co2.device_class == SensorDeviceClass.CO2
    assert co2.unit_of_measurement == CONCENTRATION_PARTS_PER_MILLION

    tvoc = make_sensor("SL_SC_CQ", "P4", {"val": 340})
    assert tvoc.state == 0.34
    assert tvoc.device_class == SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS
    assert tvoc.unit_of_measurement == CONCENTRATION_MILLIGRAMS_PER_CUBIC_METER
    assert tvoc.extra_state_attributes == {"raw": 340}


def test_tvoc_co2_sensor_battery_and_usb_voltage():
    battery = make_sensor("SL_SC_CQ", "P5", {"val": 3000, "v": 91})
    assert battery.state == 91
    assert battery.device_class == SensorDeviceClass.BATTERY
    assert battery.unit_of_measurement == PERCENTAGE

    usb_voltage = make_sensor("SL_SC_CQ", "P6", {"val": 440, "v": 4.4})
    assert usb_voltage.state == 4.4
    assert usb_voltage.device_class == SensorDeviceClass.VOLTAGE
    assert usb_voltage.unit_of_measurement == UnitOfElectricPotential.VOLT
