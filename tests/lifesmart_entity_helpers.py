import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from custom_components.lifesmart.binary_sensor import LifeSmartBinarySensor  # noqa: E402
from custom_components.lifesmart.sensor import LifeSmartSensor  # noqa: E402
from custom_components.lifesmart.switch import LifeSmartSwitch  # noqa: E402


def make_raw_device(device_type):
    return {
        "name": "Test Device",
        "devtype": device_type,
        "agt": "HUB1",
        "me": "DEVICE1",
        "ver": "1.0",
    }


def make_binary_sensor(device_type, sub_device_key, sub_device_data):
    return LifeSmartBinarySensor(
        device=None,
        raw_device_data=make_raw_device(device_type),
        sub_device_key=sub_device_key,
        sub_device_data=sub_device_data,
        client=None,
    )


def make_sensor(device_type, sub_device_key, sub_device_data):
    return LifeSmartSensor(
        device=None,
        raw_device_data=make_raw_device(device_type),
        sub_device_key=sub_device_key,
        sub_device_data=sub_device_data,
        client=None,
    )


def make_switch(device_type, sub_device_key, sub_device_data):
    return LifeSmartSwitch(
        device=None,
        raw_device_data=make_raw_device(device_type),
        sub_device_key=sub_device_key,
        sub_device_data=sub_device_data,
        client=None,
    )
