from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass

from tests.lifesmart_entity_helpers import make_binary_sensor, make_sensor


def test_gas_alarm_sound_is_binary_sound_sensor():
    gas_alarm = make_binary_sensor("SL_SC_CP", "P3", {"type": 1, "val": 1})
    assert gas_alarm.is_on is True
    assert gas_alarm.device_class == BinarySensorDeviceClass.SOUND


def test_gas_sensor_alarm_attribute_and_threshold_sensor():
    gas = make_sensor("SL_SC_CP", "P1", {"type": 1, "val": 150})
    assert gas.state == 150
    assert gas.device_class == SensorDeviceClass.GAS
    assert gas.extra_state_attributes == {"alarm": True, "raw": 150}

    threshold = make_sensor("SL_SC_CP", "P2", {"val": 120})
    assert threshold.state == 120
    assert threshold.device_class is None
    assert threshold.extra_state_attributes == {"raw": 120}
