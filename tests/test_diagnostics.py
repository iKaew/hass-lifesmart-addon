import asyncio
import importlib
from types import SimpleNamespace

from custom_components.lifesmart.const import (
    CONF_LIFESMART_APPKEY,
    CONF_LIFESMART_APPTOKEN,
    CONF_LIFESMART_USERID,
    CONF_LIFESMART_USERPASSWORD,
)
from custom_components.lifesmart.runtime_data import LifeSmartRuntimeData

diagnostics = importlib.import_module("custom_components.lifesmart.diagnostics")


def test_diagnostics_redacts_credentials_and_summarizes_devices():
    entry = SimpleNamespace(
        data={
            CONF_LIFESMART_APPKEY: "secret-key",
            CONF_LIFESMART_APPTOKEN: "secret-token",
            CONF_LIFESMART_USERID: "user@example.com",
            CONF_LIFESMART_USERPASSWORD: "secret-password",
            "region": "us",
        },
        options={},
        runtime_data=LifeSmartRuntimeData(
            client=None,
            devices=[{"devtype": "SL_SPOT"}, {"devtype": "SL_SPOT"}],
            scenes=[{"agt": "HUB1", "id": "SCENE1", "name": "Movie Night"}],
            connected=False,
            last_error="offline",
        ),
    )

    result = asyncio.run(
        diagnostics.async_get_config_entry_diagnostics(object(), entry)
    )

    assert "secret" not in repr(result)
    assert result["entry"]["region"] == "us"
    assert result["connection"] == {"connected": False, "last_error": "offline"}
    assert result["devices"]["count"] == 2
    assert result["devices"]["types"] == {"SL_SPOT": 2}
    assert result["scenes"] == {"count": 1}
