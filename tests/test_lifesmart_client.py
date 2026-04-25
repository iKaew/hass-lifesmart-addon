import asyncio
import json

import aiohttp
import pytest

from custom_components.lifesmart.lifesmart_client import LifeSmartClient


class FakeLifeSmartClient(LifeSmartClient):
    def __init__(self, remote_list=None, post_responses=None, max_timeout_retries=2):
        super().__init__(
            region="us",
            appkey="appkey",
            apptoken="apptoken",
            userid="userid",
            userpassword="password",
            max_timeout_retries=max_timeout_retries,
        )
        self.remote_list = remote_list
        self.post_responses = list(post_responses or [])
        self.post_calls = []

    async def get_ir_remote_list_async(self, agt):
        if self.remote_list is not None:
            return self.remote_list
        return await super().get_ir_remote_list_async(agt)

    async def post_async(self, url, data, headers):
        self.post_calls.append((url, data, headers))
        if not self.post_responses:
            raise AssertionError("No fake response queued for post_async")
        return self.post_responses.pop(0)


def test_normalize_ir_keys_accepts_lists_existing_json_and_raw_strings():
    client = LifeSmartClient(
        region="us",
        appkey="appkey",
        apptoken="apptoken",
        userid="userid",
        userpassword="password",
    )

    assert client._normalize_ir_keys([{"param": {"data": "ABC", "type": 1}}]) == (
        '[{"param": {"data": "ABC", "type": 1}}]'
    )
    assert client._normalize_ir_keys('[{"param":{"data":"XYZ","type":1}}]') == (
        '[{"param":{"data":"XYZ","type":1}}]'
    )
    assert client._normalize_ir_keys("RAW_IR") == json.dumps(
        [{"param": {"data": "RAW_IR", "type": 1}}]
    )


def test_resolve_ir_remote_ai_matches_device_profile_and_fallback_fields():
    client = FakeLifeSmartClient(
        remote_list={
            "ignored": "not-a-dict",
            "ai-other": {
                "category": "tv",
                "brand": "aux",
                "idx": "wrong",
                "me": "SPOT1",
            },
            "prefix-SPOT1-remote": {
                "category": "tv",
                "brand": "aux",
                "idx": "33.irxs",
            },
            "ai-by-remote-device": {
                "category": "ac",
                "brand": "aux",
                "idx": "44.irxs",
                "device_id": "SPOT2",
            },
        }
    )

    resolved_ai = asyncio.run(
        client.resolve_ir_remote_ai_async("HUB1", "SPOT1", "tv", "aux", "33.irxs")
    )
    resolved_by_device_id = asyncio.run(
        client.resolve_ir_remote_ai_async("HUB1", "SPOT2", "ac", "aux", "44.irxs")
    )

    assert resolved_ai == "prefix-SPOT1-remote"
    assert resolved_by_device_id == "ai-by-remote-device"


def test_resolve_ir_remote_ai_ignores_partial_device_id_matches():
    client = FakeLifeSmartClient(
        remote_list={
            "prefix-SPOT12-remote": {
                "category": "tv",
                "brand": "aux",
                "idx": "33.irxs",
            }
        }
    )

    resolved_ai = asyncio.run(
        client.resolve_ir_remote_ai_async("HUB1", "SPOT1", "tv", "aux", "33.irxs")
    )

    assert resolved_ai is None


def test_resolve_ir_remote_ai_returns_none_for_unexpected_remote_list_shapes():
    client = FakeLifeSmartClient(remote_list=["not", "a", "dict"])

    resolved_ai = asyncio.run(
        client.resolve_ir_remote_ai_async("HUB1", "SPOT1", "tv", "aux", "33.irxs")
    )

    assert resolved_ai is None


def test_client_generates_region_specific_and_default_urls():
    us_client = LifeSmartClient(
        region="us",
        appkey="appkey",
        apptoken="apptoken",
        userid="userid",
        userpassword="password",
    )
    default_region_client = LifeSmartClient(
        region="",
        appkey="appkey",
        apptoken="apptoken",
        userid="userid",
        userpassword="password",
    )

    assert us_client.get_api_url() == "https://api.us.ilifesmart.com/app"
    assert us_client.get_wss_url() == "wss://api.us.ilifesmart.com:8443/wsapp/"
    assert default_region_client.get_api_url() == "https://api.ilifesmart.com/app"
    assert default_region_client.get_wss_url() == "wss://api.ilifesmart.com:8443/wsapp/"


def test_post_json_retries_server_timeout_and_then_succeeds(monkeypatch):
    client = FakeLifeSmartClient(
        post_responses=[
            '{"status":"failure","message":"timeout","code":10009,"id":1}',
            '{"code":0,"message":{"devices":[]}}',
        ]
    )
    sleep_calls = []

    async def fake_sleep(delay):
        sleep_calls.append(delay)

    monkeypatch.setattr(
        "custom_components.lifesmart.lifesmart_client.asyncio.sleep", fake_sleep
    )

    response = asyncio.run(
        client._post_json("https://api.us.ilifesmart.com/app/api.EpGetAll", {"id": 1})
    )

    assert response == {"code": 0, "message": {"devices": []}}
    assert len(client.post_calls) == 2
    assert sleep_calls == [0.5]


def test_post_json_returns_timeout_response_after_retry_budget_exhausted(monkeypatch):
    client = FakeLifeSmartClient(
        post_responses=[
            '{"status":"failure","message":"timeout","code":10009,"id":1}',
            '{"status":"failure","message":"timeout","code":10009,"id":1}',
        ],
        max_timeout_retries=1,
    )
    sleep_calls = []

    async def fake_sleep(delay):
        sleep_calls.append(delay)

    monkeypatch.setattr(
        "custom_components.lifesmart.lifesmart_client.asyncio.sleep", fake_sleep
    )

    response = asyncio.run(
        client._post_json("https://api.us.ilifesmart.com/app/api.EpGetAll", {"id": 1})
    )

    assert response == {"status": "failure", "message": "timeout", "code": 10009, "id": 1}
    assert len(client.post_calls) == 2
    assert sleep_calls == [0.5]


def test_request_ids_increment_across_api_requests():
    client = FakeLifeSmartClient(
        post_responses=[
            '{"code":0,"message":{"devices":[]}}',
            '{"code":0,"message":[]}',
        ]
    )
    client._usertoken = "usertoken"

    asyncio.run(client.get_all_device_async())
    asyncio.run(client.get_all_scene_async("HUB1"))

    first_payload = json.loads(client.post_calls[0][1])
    second_payload = json.loads(client.post_calls[1][1])

    assert first_payload["id"] == 1
    assert second_payload["id"] == 2


def test_generate_wss_auth_uses_next_request_id():
    client = LifeSmartClient(
        region="us",
        appkey="appkey",
        apptoken="apptoken",
        userid="userid",
        userpassword="password",
    )
    client._usertoken = "usertoken"

    first_message = json.loads(client.generate_wss_auth())
    second_message = json.loads(client.generate_wss_auth())

    assert first_message["id"] == 1
    assert second_message["id"] == 2


def test_login_async_success_updates_credentials():
    client = FakeLifeSmartClient(
        post_responses=[
            '{"code":"success","userid":"new-user","rgn":"us","token":"temp-token"}',
            '{"code":"success","usertoken":"user-token"}',
        ]
    )

    response = asyncio.run(client.login_async())

    assert response == {"code": "success", "usertoken": "user-token"}
    assert client._userid == "new-user"
    assert client._rgn == "us"
    assert client._usertoken == "user-token"


def test_login_async_returns_failure_response_without_updating_state():
    client = FakeLifeSmartClient(post_responses=['{"code":"failure","message":"bad auth"}'])

    response = asyncio.run(client.login_async())

    assert response == {"code": "failure", "message": "bad auth"}
    assert client._userid == "userid"
    assert client._usertoken is None


def test_login_async_does_not_set_usertoken_when_second_step_fails():
    client = FakeLifeSmartClient(
        post_responses=[
            '{"code":"success","userid":"new-user","rgn":"us","token":"temp-token"}',
            '{"code":"failure","message":"auth failed"}',
        ]
    )

    response = asyncio.run(client.login_async())

    assert response == {"code": "failure", "message": "auth failed"}
    assert client._userid == "new-user"
    assert client._usertoken is None


def test_device_and_scene_calls_return_api_payloads_for_success_and_failure():
    client = FakeLifeSmartClient(
        post_responses=[
            '{"code":123,"message":"error"}',
            '{"code":0,"message":["scene-1"]}',
            '{"code":1,"message":"bad"}',
        ]
    )
    client._usertoken = "usertoken"

    devices = asyncio.run(client.get_all_device_async())
    scenes = asyncio.run(client.get_all_scene_async("HUB1"))
    failed_scenes = asyncio.run(client.get_all_scene_async("HUB1"))

    assert devices == {"code": 123, "message": "error"}
    assert scenes == ["scene-1"]
    assert failed_scenes is False


def test_scene_and_ir_send_methods_build_expected_payloads():
    client = FakeLifeSmartClient(
        post_responses=[
            '{"code":0,"message":"ok"}',
            '{"code":0,"message":"ok"}',
            '{"code":0,"message":"ok"}',
            '{"code":0,"message":"ok"}',
        ]
    )
    client._usertoken = "usertoken"

    scene_response = asyncio.run(client.set_scene_async("HUB1", "scene-9"))
    ir_key_response = asyncio.run(
        client.send_ir_key_async("HUB1", "AI1", "ME1", "tv", "aux", "power")
    )
    ir_code_response = asyncio.run(client.send_ir_code_async("HUB1", "ME1", "RAW"))
    ac_response = asyncio.run(
        client.send_ir_ackey_async(
            "HUB1", "AI1", "ME1", "ac", "aux", "power", "33.irxs", 1, 2, 24, 3, 0
        )
    )

    scene_payload = json.loads(client.post_calls[0][1])
    ir_key_payload = json.loads(client.post_calls[1][1])
    ir_code_payload = json.loads(client.post_calls[2][1])
    ac_payload = json.loads(client.post_calls[3][1])

    assert scene_response == {"code": 0, "message": "ok"}
    assert scene_payload["method"] == "SceneSet"
    assert scene_payload["params"] == {"agt": "HUB1", "id": "scene-9"}
    assert ir_key_response == {"code": 0, "message": "ok"}
    assert ir_key_payload["params"]["ai"] == "AI1"
    assert ir_key_payload["params"]["keys"] == "power"
    assert ir_code_response == {"code": 0, "message": "ok"}
    assert ir_code_payload["params"]["keys"] == json.dumps(
        [{"param": {"data": "RAW", "type": 1}}]
    )
    assert ac_response == {"code": 0, "message": "ok"}
    assert ac_payload["params"]["ai"] == "AI1"
    assert "idx" not in ac_payload["params"]


def test_send_ir_ackey_uses_idx_when_ai_is_missing():
    client = FakeLifeSmartClient(post_responses=['{"code":0,"message":"ok"}'])
    client._usertoken = "usertoken"

    asyncio.run(
        client.send_ir_ackey_async(
            "HUB1", "", "ME1", "ac", "aux", "power", "33.irxs", 1, 2, 24, 3, 0
        )
    )

    payload = json.loads(client.post_calls[0][1])

    assert payload["params"]["idx"] == "33.irxs"
    assert "ai" not in payload["params"]


def test_light_and_device_methods_return_expected_values():
    client = FakeLifeSmartClient(
        post_responses=[
            '{"code":0,"message":"on"}',
            '{"code":1,"message":"off"}',
            '{"code":0,"message":{"data":[{"idx":"P1"}]}}',
        ]
    )
    client._usertoken = "usertoken"

    on_code = asyncio.run(client.turn_on_light_swith_async("P1", "HUB1", "ME1"))
    off_code = asyncio.run(client.turn_off_light_swith_async("P1", "HUB1", "ME1"))
    epget_data = asyncio.run(client.get_epget_async("HUB1", "ME1"))

    assert on_code == 0
    assert off_code == 1
    assert epget_data == [{"idx": "P1"}]


def test_ir_query_methods_parse_messages_and_defaults():
    client = FakeLifeSmartClient(
        post_responses=[
            '{"message":{"ai-1":{"brand":"aux"}}}',
            '{"message":{"codes":["power"]}}',
            '{"message":["tv","ac"]}',
            '{"message":{"data":{"aux":"Aux"}}}',
            '{"message":{"data":["33.irxs"]}}',
            '{"message":{"data":{"power":"001"}}}',
            '{"message":[{"data":"ABC"}]}',
        ]
    )
    client._usertoken = "usertoken"

    remote_list = asyncio.run(client.get_ir_remote_list_async("HUB1"))
    remote_codes = asyncio.run(client.get_ir_remote_async("HUB1", "AI1"))
    categories = asyncio.run(client.get_category_async())
    brands = asyncio.run(client.get_brands_async("ac"))
    remote_idxs = asyncio.run(client.get_remote_idxs_async("ac", "aux"))
    codes = asyncio.run(client.get_codes_async("tv", "aux", "33.irxs", ["power"]))
    ac_codes = asyncio.run(client.get_ac_codes_async("ac", "aux", "33.irxs", "power", 1, 2, 24, 3, 0))

    codes_payload = json.loads(client.post_calls[5][1])

    assert remote_list == {"ai-1": {"brand": "aux"}}
    assert remote_codes == ["power"]
    assert categories == ["tv", "ac"]
    assert brands == {"aux": "Aux"}
    assert remote_idxs == ["33.irxs"]
    assert codes == {"power": "001"}
    assert ac_codes == [{"data": "ABC"}]
    assert codes_payload["params"]["keys"] == '["power"]'


def test_getters_return_empty_defaults_when_message_data_is_missing():
    client = FakeLifeSmartClient(
        post_responses=[
            '{"message":{}}',
            '{"message":{}}',
            '{"message":{}}',
            '{"message":{}}',
        ]
    )
    client._usertoken = "usertoken"

    brands = asyncio.run(client.get_brands_async("ac"))
    remote_idxs = asyncio.run(client.get_remote_idxs_async("ac", "aux"))
    codes = asyncio.run(client.get_codes_async("tv", "aux", "33.irxs"))
    ac_codes = asyncio.run(client.get_ac_codes_async("ac", "aux", "33.irxs", "power", 1, 2, 24, 3, 0))

    assert brands == {}
    assert remote_idxs == []
    assert codes == {}
    assert ac_codes == {}


def test_post_json_raises_for_transport_and_json_errors():
    client = FakeLifeSmartClient()

    async def raise_client_error(url, data, headers):
        raise aiohttp.ClientError("boom")

    async def return_bad_json(url, data, headers):
        return "{not-json"

    client.post_async = raise_client_error
    with pytest.raises(aiohttp.ClientError):
        asyncio.run(client._post_json("https://example.com", {"id": 1}))

    client.post_async = return_bad_json
    with pytest.raises(json.JSONDecodeError):
        asyncio.run(client._post_json("https://example.com", {"id": 1}))


def test_post_async_uses_injected_session():
    events = []

    class FakeResponse:
        async def __aenter__(self):
            events.append("response-enter")
            return self

        async def __aexit__(self, exc_type, exc, tb):
            events.append("response-exit")

        async def text(self):
            return '{"code":0}'

    class FakeSession:
        def post(self, url, data, headers):
            events.append(("post", url, data, headers))
            return FakeResponse()

    client = LifeSmartClient(
        region="us",
        appkey="appkey",
        apptoken="apptoken",
        userid="userid",
        userpassword="password",
        session=FakeSession(),
    )

    response = asyncio.run(
        client.post_async("https://example.com", "{}", {"Content-Type": "application/json"})
    )

    assert response == '{"code":0}'
    assert events[0][0] == "post"
    assert events[1:] == ["response-enter", "response-exit"]


def test_post_async_creates_client_session_when_no_session(monkeypatch):
    events = []

    class FakeResponse:
        async def __aenter__(self):
            events.append("response-enter")
            return self

        async def __aexit__(self, exc_type, exc, tb):
            events.append("response-exit")

        async def text(self):
            return '{"code":0}'

    class FakeClientSession:
        def __init__(self, timeout):
            events.append(("session-init", timeout))

        async def __aenter__(self):
            events.append("session-enter")
            return self

        async def __aexit__(self, exc_type, exc, tb):
            events.append("session-exit")

        def post(self, url, data, headers):
            events.append(("post", url, data, headers))
            return FakeResponse()

    monkeypatch.setattr(
        "custom_components.lifesmart.lifesmart_client.aiohttp.ClientSession",
        FakeClientSession,
    )

    client = LifeSmartClient(
        region="us",
        appkey="appkey",
        apptoken="apptoken",
        userid="userid",
        userpassword="password",
    )

    response = asyncio.run(
        client.post_async("https://example.com", "{}", {"Content-Type": "application/json"})
    )

    assert response == '{"code":0}'
    assert events[0][0] == "session-init"
    assert "session-enter" in events
    assert "session-exit" in events
