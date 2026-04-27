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
from homeassistant.helpers.entity import EntityCategory

from tests.lifesmart_entity_helpers import (
    make_binary_sensor,
    make_sensor,
    make_switch,
)


def test_ha_controller_switches_and_status_inputs():
    config = make_sensor("SL_JEMA", "P1", {"val": 0x02010005})
    relay = make_switch("SL_JEMA", "P2", {"type": 1, "val": 1})
    ha_switch = make_switch("SL_JEMA", "P8", {"type": 1, "val": 1})
    ha_switch_2 = make_switch("SL_JEMA", "P9", {"type": 0, "val": 0})
    ha_switch_3 = make_switch("SL_JEMA", "P10", {"type": 1, "val": 1})
    assert ha_switch.is_on is True
    assert ha_switch_2.is_on is False
    assert ha_switch_3.is_on is True
    assert relay.is_on is True
    assert config.entity_category == EntityCategory.DIAGNOSTIC
    assert config.entity_registry_enabled_default is False
    assert config.extra_state_attributes["working_mode"] == "two_wire_curtain"

    status = make_binary_sensor("SL_JEMA", "P6", {"type": 1, "val": 0})
    assert status.is_on is True
    assert status.device_class == BinarySensorDeviceClass.LOCK


def test_general_controller_documented_ports():
    config = make_sensor("SL_P", "P1", {"val": 0x8A07000A})
    output = make_switch("SL_P", "P2", {"type": 1, "val": 1})
    input_status = make_binary_sensor("SL_P", "P5", {"type": 1, "val": 0})

    assert config.state == 0x8A07000A
    assert config.device_class is None
    assert config.unit_of_measurement is None
    assert config.entity_category == EntityCategory.DIAGNOSTIC
    assert config.entity_registry_enabled_default is False
    assert config.extra_state_attributes == {
        "software_configured": True,
        "working_mode": "three_way_switch_rocker",
        "working_mode_raw": 10,
        "inching": False,
        "ctrl1_enabled": True,
        "ctrl2_enabled": True,
        "ctrl3_enabled": True,
        "auto_close_delay": 10,
        "auto_close_config": 0x7000A,
        "raw": 0x8A07000A,
    }
    assert output.is_on is True
    assert input_status.is_on is True
    assert input_status.device_class == BinarySensorDeviceClass.LOCK


def test_sl_p_status_inputs_use_val_polarity():
    for port in ("P5", "P6", "P7"):
        active = make_binary_sensor("SL_P", port, {"type": 0, "val": 0})
        inactive = make_binary_sensor("SL_P", port, {"type": 1, "val": 1})

        assert active.is_on is True
        assert inactive.is_on is False
        assert active._state_from_data(
            {"devtype": "SL_P", "idx": port, "type": 0, "val": 0}
        ) is True
        assert inactive._state_from_data(
            {"devtype": "SL_P", "idx": port, "type": 1, "val": 1}
        ) is False


def test_sl_jema_status_inputs_use_type_polarity():
    active = make_binary_sensor("SL_JEMA", "P5", {"type": 1, "val": 1})
    inactive = make_binary_sensor("SL_JEMA", "P5", {"type": 0, "val": 0})

    assert active.is_on is True
    assert inactive.is_on is False


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
