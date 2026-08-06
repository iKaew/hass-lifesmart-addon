from custom_components.lifesmart.runtime_data import (
    LifeSmartAvailabilityMixin,
    LifeSmartRuntimeData,
)


class FakeEntity(LifeSmartAvailabilityMixin):
    def __init__(self, writes):
        self._writes = writes

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
