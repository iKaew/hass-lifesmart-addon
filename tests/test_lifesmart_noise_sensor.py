from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import UnitOfSoundPressure

from tests.lifesmart_entity_helpers import make_binary_sensor, make_sensor


def test_noise_buzzer_binary_state():
    buzzer = make_binary_sensor("SL_SC_CN", "P3", {"type": 1, "val": 1})
    assert buzzer.is_on is True
    assert buzzer.device_class == BinarySensorDeviceClass.SOUND


def test_noise_sensor_value_threshold_and_correction():
    noise = make_sensor("SL_SC_CN", "P1", {"type": 1, "val": 72})
    assert noise.state == 72
    assert noise.device_class == SensorDeviceClass.SOUND_PRESSURE
    assert noise.unit_of_measurement == UnitOfSoundPressure.DECIBEL
    assert noise.extra_state_attributes == {"alarm": True, "raw": 72}

    threshold = make_sensor("SL_SC_CN", "P2", {"val": 0x140A0646})
    assert threshold.state == 0x140A0646
    assert threshold.device_class is None
    assert threshold.extra_state_attributes == {"raw": 0x140A0646}

    correction = make_sensor("SL_SC_CN", "P4", {"val": -12})
    assert correction.state == -12
    assert correction.device_class is None
    assert correction.extra_state_attributes == {"raw": -12}
