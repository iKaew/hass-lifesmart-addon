from homeassistant.components.binary_sensor import BinarySensorDeviceClass

from tests.lifesmart_entity_helpers import make_binary_sensor


def test_smart_alarm_binary_states():
    alarm = make_binary_sensor("SL_ALM", "P2", {"type": 0, "val": 0})
    assert alarm.is_on is False
    assert alarm.device_class == BinarySensorDeviceClass.SOUND
