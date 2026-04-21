from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import PERCENTAGE

from tests.lifesmart_entity_helpers import make_binary_sensor, make_sensor


def test_c100_c200_lock_battery_and_doorbell():
    battery = make_sensor("SL_LK_TY", "BAT", {"val": 88})
    assert battery.state == 88
    assert battery.device_class == SensorDeviceClass.BATTERY
    assert battery.unit_of_measurement == PERCENTAGE

    doorbell = make_binary_sensor("SL_LK_DJ", "EVTBELL", {"type": 1, "val": 0})
    assert doorbell.is_on is True
    assert doorbell.device_class == BinarySensorDeviceClass.SOUND
    assert doorbell.extra_state_attributes == {"raw": 0}
