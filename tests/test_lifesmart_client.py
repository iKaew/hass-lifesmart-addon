import asyncio
import json

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
        return self.remote_list

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
