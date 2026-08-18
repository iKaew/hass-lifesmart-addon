"""Tests for native LifeSmart scene entities."""

import asyncio
import importlib
from types import SimpleNamespace

import pytest

from custom_components.lifesmart.const import DOMAIN, HUB_ID_KEY
from custom_components.lifesmart.runtime_data import LifeSmartRuntimeData

scene_module = importlib.import_module("custom_components.lifesmart.scene")

_UNSET = object()


class FakeClient:
    def __init__(self, response=_UNSET, error=None):
        self.response = {"code": 0} if response is _UNSET else response
        self.error = error
        self.calls = []

    async def set_scene_async(self, hub_id, scene_id):
        self.calls.append((hub_id, scene_id))
        if self.error is not None:
            raise self.error
        return self.response


def make_scene(client=None):
    return scene_module.LifeSmartScene(
        client or FakeClient(),
        {HUB_ID_KEY: "HUB1", "id": "SCENE1", "name": "Movie Night"},
    )


def test_scene_setup_creates_native_entities():
    client = FakeClient()
    entry = SimpleNamespace(
        runtime_data=LifeSmartRuntimeData(
            client=client,
            devices=[],
            scenes=[
                {HUB_ID_KEY: "HUB1", "id": "SCENE1", "name": "Movie Night"},
                {HUB_ID_KEY: "HUB2", "id": "SCENE1", "name": "Away"},
            ],
        )
    )
    added = []

    asyncio.run(
        scene_module.async_setup_entry(
            object(), entry, lambda entities: added.extend(entities)
        )
    )

    assert [entity.name for entity in added] == ["Movie Night", "Away"]
    assert [entity.unique_id for entity in added] == [
        "HUB1_SCENE1",
        "HUB2_SCENE1",
    ]
    assert added[0].device_info["identifiers"] == {(DOMAIN, "HUB1")}


@pytest.mark.parametrize("response", [{"code": 0}, {"code": "success"}, 0])
def test_scene_activation_calls_lifesmart(response):
    client = FakeClient(response=response)
    scene = make_scene(client)

    asyncio.run(scene.async_activate())

    assert client.calls == [("HUB1", "SCENE1")]


@pytest.mark.parametrize(
    "response",
    [{"code": 1}, {"code": False}, 1, False, None, "invalid"],
)
def test_scene_activation_reports_rejected_request(response):
    client = FakeClient(response=response)
    scene = make_scene(client)

    with pytest.raises(scene_module.HomeAssistantError) as error:
        asyncio.run(scene.async_activate())

    assert error.value.translation_key == "scene_activation_rejected"


def test_scene_activation_wraps_client_error():
    client = FakeClient(error=RuntimeError("private API failure"))
    scene = make_scene(client)

    with pytest.raises(scene_module.HomeAssistantError) as error:
        asyncio.run(scene.async_activate())

    assert error.value.translation_key == "scene_activation_failed"
    assert isinstance(error.value.__cause__, RuntimeError)
