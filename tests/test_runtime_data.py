from custom_components.lifesmart.runtime_data import (
    LifeSmartAvailabilityMixin,
    LifeSmartRuntimeData,
    get_runtime_data,
)
from custom_components.lifesmart.const import DOMAIN


class FakeEntity(LifeSmartAvailabilityMixin):
    def __init__(self, writes, hass=object()):
        self._writes = writes
        self.hass = hass

    def schedule_update_ha_state(self):
        self._writes.append(True)


def test_runtime_connection_updates_entity_availability():
    writes = []
    entity = FakeEntity(writes)
    runtime = LifeSmartRuntimeData(client=None, devices=[])

    runtime.track_entities([entity])
    assert entity.available is False
    runtime.set_connected(True)

    assert entity._lifesmart_runtime is runtime
    assert runtime.connected is True
    assert entity.available is True
    assert writes == [True]

    runtime.set_connected(False, "offline")
    assert entity.available is False
    assert runtime.last_error == "offline"
    assert writes == [True, True]


def test_runtime_ignores_unchanged_connection_state():
    writes = []
    entity = FakeEntity(writes)
    runtime = LifeSmartRuntimeData(client=None, devices=[])
    runtime.track_entities([entity])

    runtime.set_connected(False)
    runtime.set_connected(True)
    runtime.set_connected(True)

    assert writes == [True]


def test_runtime_does_not_schedule_entity_before_home_assistant_adds_it():
    writes = []
    entity = FakeEntity(writes, hass=None)
    runtime = LifeSmartRuntimeData(client=None, devices=[])
    runtime.track_entities([entity])

    runtime.set_connected(True)

    assert entity.available is True
    assert writes == []


def test_entity_is_available_before_it_is_tracked():
    assert FakeEntity([]).available is True


def test_get_runtime_data_returns_config_entry_runtime():
    runtime = LifeSmartRuntimeData(client=object(), devices=[])
    entry = type("Entry", (), {"runtime_data": runtime})()

    assert get_runtime_data(object(), entry) is runtime


def test_get_runtime_data_builds_legacy_test_runtime():
    client = object()
    manager = object()
    listener = object()
    devices = [{"agt": "hub-1"}]
    legacy = {
        "client": client,
        "devices": devices,
        "exclude_devices": ["device-1"],
        "exclude_hubs": ["hub-2"],
        "ai_include_hubs": ["hub-1"],
        "ai_include_items": ["device-2"],
        "state_manager": manager,
        "update_listener": listener,
    }
    hass = type("Hass", (), {"data": {DOMAIN: {"entry-1": legacy}}})()
    entry = type("Entry", (), {"entry_id": "entry-1"})()

    runtime = get_runtime_data(hass, entry)

    assert runtime.client is client
    assert runtime.devices is devices
    assert runtime.exclude_devices == ["device-1"]
    assert runtime.exclude_hubs == ["hub-2"]
    assert runtime.ai_include_hubs == ["hub-1"]
    assert runtime.ai_include_items == ["device-2"]
    assert runtime.state_manager is manager
    assert runtime.update_listener is listener
