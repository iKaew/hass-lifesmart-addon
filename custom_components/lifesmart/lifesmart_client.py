"""The LifeSmart API Client."""

import hashlib
import json
import logging
import time

import aiohttp

_LOGGER = logging.getLogger(__name__)


class LifeSmartClient:
    """A class for manage LifeSmart API."""

    def __init__(
        self,
        region,
        appkey,
        apptoken,
        userid,
        userpassword,
    ) -> None:
        """Initialize LifeSmart client."""
        self._region = region
        self._appkey = appkey
        self._apptoken = apptoken
        self._userid = userid
        self._userpassword = userpassword
        self._usertoken = None

    async def get_all_device_async(self):
        """Get all devices belong to current user."""
        url = self.get_api_url() + "/api.EpGetAll"
        tick = int(time.time())
        sdata = "method:EpGetAll," + self.__generate_time_and_credential_data(tick)

        send_values = {
            "id": 1,
            "method": "EpGetAll",
            "system": self.__generate_system_request_body(tick, sdata),
        }
        header = self.__generate_header()
        send_data = json.dumps(send_values)

        response = json.loads(await self.post_async(url, send_data, header))
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
            "id": 1,
            "method": "SceneGet",
            "params": {
                "agt": agt,
            },
            "system": self.__generate_system_request_body(tick, sdata),
        }
        header = self.__generate_header()
        send_data = json.dumps(send_values)
        response = json.loads(await self.post_async(url, send_data, header))
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
        header = self.__generate_header()
        send_data = json.dumps(login_data)
        response = json.loads(await self.post_async(url, send_data, header))
        if response["code"] != "success":
            return response

        # Use temporary token to get usertoken
        url = self.get_api_url() + "/auth.do_auth"
        auth_data = {
            "userid": response["userid"],
            "token": response["token"],
            "appkey": self._appkey,
            "rgn": self._region,
        }
        if self._userid != response["userid"]:
            self._userid = response["userid"]

        send_data = json.dumps(auth_data)
        response = json.loads(await self.post_async(url, send_data, header))
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
            "id": 101,
            "method": "SceneSet",
            "params": {
                "agt": agt,
                "id": id,
            },
            "system": self.__generate_system_request_body(tick, sdata),
        }
        header = self.__generate_header()
        send_data = json.dumps(send_values)

        return json.loads(await self.post_async(url, send_data, header))

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
            "id": 1,
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
        header = self.__generate_header()
        send_data = json.dumps(send_values)

        return json.loads(await self.post_async(url, send_data, header))

    async def send_ir_code_async(self, agt, me, keys):
        """Send an IR code to a specific device."""

        url = self.get_api_url() + "/irapi.SendCodes"
        tick = int(time.time())
        # keys = str(keys)
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
            "id": 1,
            "method": "SendCodes",
            "params": {
                "agt": agt,
                "me": me,
                "keys": keys,
            },
            "system": self.__generate_system_request_body(tick, sdata),
        }
        header = self.__generate_header()
        send_data = json.dumps(send_values)
        _LOGGER.debug("ir code req: %s", str(send_data))
        response = json.loads(await self.post_async(url, send_data, header))
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
        power,
        mode,
        temp,
        wind,
        swing,
    ):
        """Send an IR AIR Conditioner Key to a specific device."""
        url = self.get_api_url() + "/irapi.SendACKeys"
        tick = int(time.time())
        # keys = str(keys)
        sdata = (
            "method:SendACKeys,agt:"
            + agt
            + ",ai:"
            + ai
            + ",brand:"
            + brand
            + ",category:"
            + category
            + ",key:"
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
        _LOGGER.debug("sendackey: %s", str(sdata))
        send_values = {
            "id": 1,
            "method": "SendACKeys",
            "params": {
                "agt": agt,
                "me": me,
                "category": category,
                "brand": brand,
                "ai": ai,
                "key": key,
                "power": power,
                "mode": mode,
                "temp": temp,
                "wind": wind,
                "swing": swing,
            },
            "system": self.__generate_system_request_body(tick, sdata),
        }
        header = self.__generate_header()
        send_data = json.dumps(send_values)

        response = json.loads(await self.post_async(url, send_data, header))
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
            "id": 1,
            "method": "EpSet",
            "system": self.__generate_system_request_body(tick, sdata),
            "params": {"agt": agt, "me": me, "idx": idx, "type": type, "val": val},
        }

        header = self.__generate_header()
        send_data = json.dumps(send_values)

        _LOGGER.debug("epset_req: %s", str(send_data))
        response = json.loads(await self.post_async(url, send_data, header))
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
            "id": 1,
            "method": "EpGet",
            "system": self.__generate_system_request_body(tick, sdata),
            "params": {"agt": agt, "me": me},
        }
        header = self.__generate_header()
        send_data = json.dumps(send_values)

        response = json.loads(await self.post_async(url, send_data, header))
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
            "id": 1,
            "method": "GetRemoteList",
            "params": {"agt": agt},
            "system": self.__generate_system_request_body(tick, sdata),
        }
        header = self.__generate_header()
        send_data = json.dumps(send_values)

        response = json.loads(await self.post_async(url, send_data, header))
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
            "id": 1,
            "method": "GetRemote",
            "params": {"agt": agt, "ai": ai, "needKeys": 2},
            "system": self.__generate_system_request_body(tick, sdata),
        }
        header = self.__generate_header()
        send_data = json.dumps(send_values)

        response = json.loads(await self.post_async(url, send_data, header))
        _LOGGER.debug("get_ir_remote_res: %s", str(response))
        return response["message"]["codes"]

    async def post_async(self, url, data, headers):
        """Async method to make a POST api call."""
        async with aiohttp.ClientSession() as session:
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

    def __generate_system_request_body(self, tick, data):
        """Generate system node in request body which contain credential and signature."""
        return {
            "ver": "1.0",
            "lang": "en",
            "userid": self._userid,
            "appkey": self._appkey,
            "time": tick,
            "sign": self.__get_signature(data),
        }

    def __generate_time_and_credential_data(self, tick):
        """Generate default parameter required in body."""

        return (
            "time:"
            + str(tick)
            + ",userid:"
            + self._userid
            + ",usertoken:"
            + self._usertoken
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
            "id": 1,
            "method": "WbAuth",
            "system": self.__generate_system_request_body(tick, sdata),
        }
        return json.dumps(send_values)
