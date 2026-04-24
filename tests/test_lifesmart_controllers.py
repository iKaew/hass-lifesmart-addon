from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import (
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    CONCENTRATION_PARTS_PER_MILLION,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfFrequency,
    UnitOfTemperature,
)

from tests.lifesmart_entity_helpers import (
    make_binary_sensor,
    make_sensor,
    make_switch,
)


def test_ha_controller_switches_and_status_inputs():
    ha_switch = make_switch("SL_JEMA", "P8", {"type": 1, "val": 1})
    assert ha_switch.is_on is True

    status = make_binary_sensor("SL_JEMA", "P6", {"type": 1, "val": 0})
    assert status.is_on is True
    assert status.device_class == BinarySensorDeviceClass.LOCK


def test_485_controller_switch_and_electrical_sensors():
    relay = make_switch("V_485_P", "L1", {"type": 1, "val": 1})
    assert relay.is_on is True

    voltage = make_sensor("V_485_P", "EV", {"v": 230.2, "val": 0})
    assert voltage.state == 230.2
    assert voltage.device_class == SensorDeviceClass.VOLTAGE
    assert voltage.unit_of_measurement == UnitOfElectricPotential.VOLT

    current = make_sensor("V_485_P", "EI1", {"v": 5.4, "val": 0})
    assert current.state == 5.4
    assert current.device_class == SensorDeviceClass.CURRENT
    assert current.unit_of_measurement == UnitOfElectricCurrent.AMPERE

    frequency = make_sensor("V_485_P", "EF", {"v": 50, "val": 0})
    assert frequency.state == 50
    assert frequency.device_class == SensorDeviceClass.FREQUENCY
    assert frequency.unit_of_measurement == UnitOfFrequency.HERTZ


def test_485_controller_environment_and_air_quality_sensors():
    temperature = make_sensor("V_485_P", "T", {"val": 236})
    assert temperature.state == 23.6
    assert temperature.device_class == SensorDeviceClass.TEMPERATURE
    assert temperature.unit_of_measurement == UnitOfTemperature.CELSIUS

    pm10 = make_sensor("V_485_P", "PM1", {"v": 22, "val": 0})
    assert pm10.state == 22
    assert pm10.device_class == SensorDeviceClass.PM10
    assert pm10.unit_of_measurement == CONCENTRATION_MICROGRAMS_PER_CUBIC_METER

    co2 = make_sensor("V_485_P", "CO2PPM", {"v": 612, "val": 0})
    assert co2.state == 612
    assert co2.device_class == SensorDeviceClass.CO2
    assert co2.unit_of_measurement == CONCENTRATION_PARTS_PER_MILLION
