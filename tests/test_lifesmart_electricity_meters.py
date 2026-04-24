import pytest
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import UnitOfEnergy, UnitOfPower

from tests.lifesmart_entity_helpers import make_sensor


def test_eliq_meter_average_power():
    power = make_sensor("ELIQ_EM", "EPA", {"val": 420})
    assert power.state == 420
    assert power.device_class == SensorDeviceClass.POWER
    assert power.unit_of_measurement == UnitOfPower.WATT
    assert power.extra_state_attributes == {"raw": 420}


def test_dlt_meter_energy_and_power_sensors():
    energy = make_sensor("V_DLT_645_P", "EE", {"v": 12.5, "val": 1095237632})
    assert energy.state == 12.5
    assert energy.device_class == SensorDeviceClass.ENERGY
    assert energy.unit_of_measurement == UnitOfEnergy.KILO_WATT_HOUR

    power = make_sensor("V_DLT_645_P", "EP", {"val": 1024913643})
    assert power.state == pytest.approx(0.03685085)
    assert power.device_class == SensorDeviceClass.POWER
    assert power.unit_of_measurement == UnitOfPower.WATT


def test_dlt_meter_appendix_alias_power_sensor():
    power = make_sensor("V_DLT645_P", "EP", {"v": 42, "val": 0})
    assert power.state == 42
    assert power.device_class == SensorDeviceClass.POWER
    assert power.unit_of_measurement == UnitOfPower.WATT
