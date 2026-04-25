"""The LifeSmart API Client."""

import asyncio
import hashlib
import itertools
import json
import logging
import time
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)
DEFAULT_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15)
SERVER_TIMEOUT_CODE = 10009
SERVER_TIMEOUT_MESSAGE = "timeout"


class LifeSmartClient:
    """A class for manage LifeSmart API."""

    def __init__(
        self,
        region,
        appkey,
        apptoken,
        userid,
        userpassword,
        session: aiohttp.ClientSession | None = None,
        request_timeout: aiohttp.ClientTimeout | None = None,
        max_timeout_retries: int = 2,
    ) -> None:
        """Initialize LifeSmart client."""
        self._region = region
        self._appkey = appkey
        self._apptoken = apptoken
        self._userid = userid
        self._userpassword = userpassword
        self._usertoken = None
        self._rgn = None
        self._session = session
        self._request_timeout = request_timeout or DEFAULT_REQUEST_TIMEOUT
        self._max_timeout_retries = max_timeout_retries
        self._request_ids = itertools.count(1)

    async def get_all_device_async(self):
        """Get all devices belong to current user."""
        url = self.get_api_url() + "/api.EpGetAll"
        tick = int(time.time())
        sdata = "method:EpGetAll," + self.__generate_time_and_credential_data(tick)

        send_values = {
            "id": self._next_request_id(),
            "method": "EpGetAll",
            "system": self.__generate_system_request_body(tick, sdata),
        }
        response = await self._post_json(url, send_values)
        _LOGGER.debug("EpGetAll_res: %s", response)
        if response["code"] == 0:
            return response["message"]
        return response

    async def get_all_scene_async(self, agt):
        """Get all scenes belong to current user."""
        url = self.get_api_url() + "/api.SceneGet"
        tick = int(time.time())
        sdata = (
            "method:SceneGet,agt:"
            + agt
            + ","
            + self.__generate_time_and_credential_data(tick)
        )
        send_values = {
            "id": self._next_request_id(),
            "method": "SceneGet",
            "params": {
                "agt": agt,
            },
            "system": self.__generate_system_request_body(tick, sdata),
        }
        response = await self._post_json(url, send_values)
        if response["code"] == 0:
            return response["message"]
        return False

    async def login_async(self):
        """Login to LifeSmart service to get user token."""
        # Get temporary token
        url = self.get_api_url() + "/auth.login"
        login_data = {
            "uid": self._userid,
            "pwd": self._userpassword,
            "appkey": self._appkey,
        }
        response = await self._post_json(url, login_data)
        if response["code"] != "success":
            return response

        self._userid = response["userid"]
        self._rgn = response["rgn"]

        # Use temporary token to get usertoken
        url = self.get_api_url() + "/auth.do_auth"
        auth_data = {
            "userid": self._userid,
            "token": response["token"],
            "appkey": self._appkey,
            "rgn": self._rgn,
        }

        response = await self._post_json(url, auth_data)
        if response["code"] == "success":
            self._usertoken = response["usertoken"]

        return response

    async def set_scene_async(self, agt, id):
        """Set the scene by scene id to LifeSmart."""
        url = self.get_api_url() + "/api.SceneSet"
        tick = int(time.time())
        # keys = str(keys)
        sdata = (
            "method:SceneSet,agt:"
            + agt
            + ",id:"
            + id
            + ","
            + self.__generate_time_and_credential_data(tick)
        )
        send_values = {
            "id": self._next_request_id(),
            "method": "SceneSet",
            "params": {
                "agt": agt,
                "id": id,
            },
            "system": self.__generate_system_request_body(tick, sdata),
        }
        return await self._post_json(url, send_values)

    async def send_ir_key_async(self, agt, ai, me, category, brand, keys):
        """Send an IR key to a specific device."""
        url = self.get_api_url() + "/irapi.SendKeys"
        tick = int(time.time())
        # keys = str(keys)
        sdata = (
            "method:SendKeys,agt:"
            + agt
            + ",ai:"
            + ai
            + ",brand:"
            + brand
            + ",category:"
            + category
            + ",keys:"
            + keys
            + ",me:"
            + me
            + ","
            + self.__generate_time_and_credential_data(tick)
        )
        send_values = {
            "id": self._next_request_id(),
            "method": "SendKeys",
            "params": {
                "agt": agt,
                "me": me,
                "category": category,
                "brand": brand,
                "ai": ai,
                "keys": keys,
            },
            "system": self.__generate_system_request_body(tick, sdata),
        }
        return await self._post_json(url, send_values)

    def _normalize_ir_keys(self, keys):
        """Normalize IR keys into the SendCodes JSON string format."""
        if isinstance(keys, (list, tuple)):
            return json.dumps(keys)

        if isinstance(keys, str):
            try:
                parsed = json.loads(keys)
                if isinstance(parsed, list):
                    return keys
            except ValueError:
                pass

            return json.dumps([{"param": {"data": keys, "type": 1}}])

        return json.dumps([{"param": {"data": str(keys), "type": 1}}])

    async def send_ir_code_async(self, agt, me, keys):
        """Send an IR code to a specific device."""

        keys = self._normalize_ir_keys(keys)
        url = self.get_api_url() + "/irapi.SendCodes"
        tick = int(time.time())
        sdata = (
            "method:SendCodes,agt:"
            + agt
            + ",keys:"
            + keys
            + ",me:"
            + me
            + ","
            + self.__generate_time_and_credential_data(tick)
        )
        send_values = {
            "id": self._next_request_id(),
            "method": "SendCodes",
            "params": {
                "agt": agt,
                "me": me,
                "keys": keys,
            },
            "system": self.__generate_system_request_body(tick, sdata),
        }
        _LOGGER.debug("Sending IR code request for agt=%s me=%s", agt, me)
        response = await self._post_json(url, send_values)
        _LOGGER.debug("ir code res: %s", str(response))
        return response

    async def send_ir_ackey_async(
        self,
        agt,
        ai,
        me,
        category,
        brand,
        key,
        idx,
        power,
        mode,
        temp,
        wind,
        swing,
    ):
        """Send an IR AIR Conditioner Key to a specific device."""
        url = self.get_api_url() + "/irapi.SendACKeys"
        tick = int(time.time())
        params = {
            "agt": agt,
            "me": me,
            "category": category,
            "brand": brand,
            "key": key,
            "power": power,
            "mode": mode,
            "temp": temp,
            "wind": wind,
            "swing": swing,
        }

        if ai:
            params["ai"] = ai
            sdata = (
                "method:SendACKeys,agt:"
                + agt
                + ",ai:"
                + ai
                + ",brand:"
                + brand
                + ",category:"
                + category
            )
        else:
            params["idx"] = idx
            sdata = (
                "method:SendACKeys,agt:"
                + agt
                + ",brand:"
                + brand
                + ",category:"
                + category
                + ",idx:"
                + idx
            )

        sdata += (
            ",key:"
            + key
            + ",me:"
            + me
            + ",mode:"
            + str(mode)
            + ",power:"
            + str(power)
            + ",swing:"
            + str(swing)
            + ",temp:"
            + str(temp)
            + ",wind:"
            + str(wind)
            + ","
            + self.__generate_time_and_credential_data(tick)
        )
        send_values = {
            "id": self._next_request_id(),
            "method": "SendACKeys",
            "params": params,
            "system": self.__generate_system_request_body(tick, sdata),
        }
        _LOGGER.debug("Sending AC IR key request for agt=%s me=%s", agt, me)
        response = await self._post_json(url, send_values)
        _LOGGER.debug("sendackey_res: %s", str(response))
        return response

    async def turn_on_light_swith_async(self, idx, agt, me):
        """Turn on light async."""
        return await self.send_epset_async("0x81", 1, idx, agt, me)

    async def turn_off_light_swith_async(self, idx, agt, me):
        """Turn off light async."""
        return await self.send_epset_async("0x80", 0, idx, agt, me)

    async def send_epset_async(self, type, val, idx, agt, me):
        """Send a command to sepcific device."""
        url = self.get_api_url() + "/api.EpSet"
        tick = int(time.time())
        sdata = (
            "method:EpSet,agt:"
            + agt
            + ",idx:"
            + idx
            + ",me:"
            + me
            + ",type:"
            + type
            + ",val:"
            + str(val)
            + ","
            + self.__generate_time_and_credential_data(tick)
        )
        send_values = {
            "id": self._next_request_id(),
            "method": "EpSet",
            "system": self.__generate_system_request_body(tick, sdata),
            "params": {"agt": agt, "me": me, "idx": idx, "type": type, "val": val},
        }

        _LOGGER.debug(
            "Sending EpSet request for agt=%s me=%s idx=%s type=%s",
            agt,
            me,
            idx,
            type,
        )
        response = await self._post_json(url, send_values)
        _LOGGER.debug("epset_res: %s", str(response))
        return response["code"]

    async def get_epget_async(self, agt, me):
        """Get device info."""
        url = self.get_api_url() + "/api.EpGet"
        tick = int(time.time())
        sdata = (
            "method:EpGet,agt:"
            + agt
            + ",me:"
            + me
            + ","
            + self.__generate_time_and_credential_data(tick)
        )
        send_values = {
            "id": self._next_request_id(),
            "method": "EpGet",
            "system": self.__generate_system_request_body(tick, sdata),
            "params": {"agt": agt, "me": me},
        }
        response = await self._post_json(url, send_values)
        _LOGGER.debug("epget_res: %s", str(response))
        return response["message"]["data"]

    async def get_ir_remote_list_async(self, agt):
        """Get remote list for a specific station."""
        url = self.get_api_url() + "/irapi.GetRemoteList"

        tick = int(time.time())
        sdata = (
            "method:GetRemoteList,agt:"
            + agt
            + ","
            + self.__generate_time_and_credential_data(tick)
        )
        send_values = {
            "id": self._next_request_id(),
            "method": "GetRemoteList",
            "params": {"agt": agt},
            "system": self.__generate_system_request_body(tick, sdata),
        }
        response = await self._post_json(url, send_values)
        _LOGGER.debug("GetRemoteList_res: %s", str(response))
        return response["message"]

    async def get_ir_remote_async(self, agt, ai):
        """Get a remote setting for sepcific device."""
        url = self.get_api_url() + "/irapi.GetRemote"

        tick = int(time.time())
        sdata = (
            "method:GetRemote,agt:"
            + agt
            + ",ai:"
            + ai
            + ",needKeys:2"
            + ","
            + self.__generate_time_and_credential_data(tick)
        )
        send_values = {
            "id": self._next_request_id(),
            "method": "GetRemote",
            "params": {"agt": agt, "ai": ai, "needKeys": 2},
            "system": self.__generate_system_request_body(tick, sdata),
        }
        response = await self._post_json(url, send_values)
        _LOGGER.debug("get_ir_remote_res: %s", str(response))
        return response["message"]["codes"]

    async def resolve_ir_remote_ai_async(self, agt, me, category, brand, idx):
        """Resolve the remote list entry key (ai) for a device/brand/profile."""
        remote_list = await self.get_ir_remote_list_async(agt)
        if not isinstance(remote_list, dict):
            return None

        for ai, remote_info in remote_list.items():
            if not isinstance(remote_info, dict):
                continue

            remote_category = str(remote_info.get("category", ""))
            remote_brand = str(remote_info.get("brand", ""))
            remote_idx = str(remote_info.get("idx", ""))
            remote_me = str(
                remote_info.get("me")
                or remote_info.get("device_id")
                or remote_info.get("dev")
                or ""
            )

            device_matches = self._ai_matches_device(ai, me) or remote_me == me
            profile_matches = (
                remote_category == category
                and remote_brand == brand
                and remote_idx == idx
            )

            if device_matches and profile_matches:
                return ai

        return None

    async def get_category_async(self):
        """Get IR remote categories."""
        url = self.get_api_url() + "/irapi.GetCategory"
        tick = int(time.time())
        sdata = "method:GetCategory," + self.__generate_time_and_credential_data(
            tick, userid="10001", usertoken="10001"
        )
        send_values = {
            "id": self._next_request_id(),
            "method": "GetCategory",
            "system": self.__generate_system_request_body(
                tick, sdata, userid="10001", usertoken="10001"
            ),
        }
        response = await self._post_json(url, send_values)
        _LOGGER.debug("GetCategory_res: %s", str(response))
        return response.get("message", [])

    async def get_brands_async(self, category):
        """Get IR remote brands for a category."""
        url = self.get_api_url() + "/irapi.GetBrands"
        tick = int(time.time())
        sdata = (
            "method:GetBrands,category:"
            + category
            + ","
            + self.__generate_time_and_credential_data(
                tick, userid="10001", usertoken="10001"
            )
        )
        send_values = {
            "id": self._next_request_id(),
            "method": "GetBrands",
            "params": {"category": category},
            "system": self.__generate_system_request_body(
                tick, sdata, userid="10001", usertoken="10001"
            ),
        }
        response = await self._post_json(url, send_values)
        _LOGGER.debug("GetBrands_res: %s", str(response))
        return response.get("message", {}).get("data", {})

    async def get_remote_idxs_async(self, category, brand):
        """Get remote indexes for a category and brand."""
        url = self.get_api_url() + "/irapi.GetRemoteIdxs"
        tick = int(time.time())
        sdata = (
            "method:GetRemoteIdxs,brand:"
            + brand
            + ",category:"
            + category
            + ","
            + self.__generate_time_and_credential_data(
                tick, userid="10001", usertoken="10001"
            )
        )
        send_values = {
            "id": self._next_request_id(),
            "method": "GetRemoteIdxs",
            "params": {"category": category, "brand": brand},
            "system": self.__generate_system_request_body(
                tick, sdata, userid="10001", usertoken="10001"
            ),
        }
        response = await self._post_json(url, send_values)
        _LOGGER.debug("GetRemoteIdxs_res: %s", str(response))
        return response.get("message", {}).get("data", [])

    async def get_codes_async(self, category, brand, idx, keys=None):
        """Get IR codes for a remote."""
        url = self.get_api_url() + "/irapi.GetCodes"
        tick = int(time.time())
        params_str = f"method:GetCodes,brand:{brand},category:{category},idx:{idx}"
        if keys:
            keys_json = json.dumps(keys) if isinstance(keys, list) else keys
            params_str += f",keys:{keys_json}"
        params_str += "," + self.__generate_time_and_credential_data(
            tick, userid="10001", usertoken="10001"
        )

        params = {"category": category, "brand": brand, "idx": idx}
        if keys:
            params["keys"] = json.dumps(keys) if isinstance(keys, list) else keys

        send_values = {
            "id": self._next_request_id(),
            "method": "GetCodes",
            "params": params,
            "system": self.__generate_system_request_body(
                tick, params_str, userid="10001", usertoken="10001"
            ),
        }
        response = await self._post_json(url, send_values)
        _LOGGER.debug("GetCodes_res: %s", str(response))
        return response.get("message", {}).get("data", {})

    async def get_ac_codes_async(
        self, category, brand, idx, key, power, mode, temp, wind, swing
    ):
        """Get AC IR codes."""
        url = self.get_api_url() + "/irapi.GetACCodes"
        tick = int(time.time())
        sdata = (
            "method:GetACCodes,brand:"
            + brand
            + ",category:"
            + category
            + ",idx:"
            + idx
            + ",key:"
            + key
            + ",mode:"
            + str(mode)
            + ",power:"
            + str(power)
            + ",swing:"
            + str(swing)
            + ",temp:"
            + str(temp)
            + ",wind:"
            + str(wind)
            + ","
            + self.__generate_time_and_credential_data(
                tick, userid="10001", usertoken="10001"
            )
        )
        send_values = {
            "id": self._next_request_id(),
            "method": "GetACCodes",
            "params": {
                "category": category,
                "brand": brand,
                "idx": idx,
                "key": key,
                "power": power,
                "mode": mode,
                "temp": temp,
                "wind": wind,
                "swing": swing,
            },
            "system": self.__generate_system_request_body(
                tick, sdata, userid="10001", usertoken="10001"
            ),
        }
        response = await self._post_json(url, send_values)
        _LOGGER.debug("GetACCodes_res: %s", str(response))
        return response.get("message", [])

    def _ai_matches_device(self, ai: str, me: str) -> bool:
        """Return whether an AI identifier belongs to the target device."""
        if ai == me:
            return True

        return me in ai.replace(":", "-").split("-")

    def _next_request_id(self) -> int:
        """Return the next outbound request identifier."""
        return next(self._request_ids)

    async def _post_json(self, url: str, payload: dict[str, Any]) -> Any:
        """Send a JSON payload and decode the JSON response."""
        for attempt in range(self._max_timeout_retries + 1):
            try:
                response_text = await self.post_async(
                    url, json.dumps(payload), self.__generate_header()
                )
            except (aiohttp.ClientError, TimeoutError) as err:
                _LOGGER.error("LifeSmart API request failed for %s: %s", url, err)
                raise

            try:
                response = json.loads(response_text)
            except json.JSONDecodeError as err:
                _LOGGER.error(
                    "LifeSmart API returned invalid JSON for %s: %s", url, err
                )
                raise

            if not self._is_server_timeout_response(response):
                return response

            if attempt >= self._max_timeout_retries:
                return response

            delay = 0.5 * (attempt + 1)
            _LOGGER.warning(
                "LifeSmart API timeout for %s, retrying in %.1fs (%s/%s)",
                url,
                delay,
                attempt + 1,
                self._max_timeout_retries,
            )
            await asyncio.sleep(delay)

        return response

    def _is_server_timeout_response(self, response: Any) -> bool:
        """Return whether the API response is a retryable server timeout."""
        return (
            isinstance(response, dict)
            and response.get("code") == SERVER_TIMEOUT_CODE
            and str(response.get("message", "")).lower() == SERVER_TIMEOUT_MESSAGE
        )

    async def post_async(self, url, data, headers):
        """Async method to make a POST api call."""
        if self._session is not None:
            async with self._session.post(url, data=data, headers=headers) as response:
                return await response.text()

        async with aiohttp.ClientSession(timeout=self._request_timeout) as session:
            async with session.post(url, data=data, headers=headers) as response:
                return await response.text()

    def __get_signature(self, data):
        """Generate signature required by LifeSmart API."""
        return hashlib.md5(data.encode(encoding="UTF-8")).hexdigest()

    def get_api_url(self):
        """Generate api URL."""
        if self._region == "":
            return "https://api.ilifesmart.com/app"

        return "https://api." + self._region + ".ilifesmart.com/app"

    def get_wss_url(self):
        """Generate websocket (wss) URL."""

        if self._region == "":
            return "wss://api.ilifesmart.com:8443/wsapp/"

        return "wss://api." + self._region + ".ilifesmart.com:8443/wsapp/"

    def __generate_system_request_body(self, tick, data, userid=None, usertoken=None):
        """Generate system node in request body which contain credential and signature."""
        uid = userid or self._userid
        return {
            "ver": "1.0",
            "lang": "en",
            "userid": uid,
            "appkey": self._appkey,
            "time": tick,
            "sign": self.__get_signature(data),
        }

    def __generate_time_and_credential_data(self, tick, userid=None, usertoken=None):
        """Generate default parameter required in body."""
        uid = userid or self._userid
        utoken = usertoken or self._usertoken

        return (
            "time:"
            + str(tick)
            + ",userid:"
            + uid
            + ",usertoken:"
            + utoken
            + ",appkey:"
            + self._appkey
            + ",apptoken:"
            + self._apptoken
        )

    def __generate_header(self):
        """Generate default http header required by LifeSmart."""
        return {"Content-Type": "application/json"}

    def generate_wss_auth(self):
        """Generate authentication message with signature for wss connection."""
        tick = int(time.time())
        sdata = "method:WbAuth," + self.__generate_time_and_credential_data(tick)

        send_values = {
            "id": self._next_request_id(),
            "method": "WbAuth",
            "system": self.__generate_system_request_body(tick, sdata),
        }
        return json.dumps(send_values)
