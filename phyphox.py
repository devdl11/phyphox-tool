import aiohttp
from dataclasses import dataclass
from typing import List
import time


@dataclass
class DataFrame:
    t: float
    data: object

    def toJson(self):
        return {"time": self.t, "data": self.data}


# TODO: create a parent class Phyphox from which we implement different devices
class PhyphoxPhone:
    CONNECTION_ERROR = (ConnectionError, aiohttp.ClientConnectionError, aiohttp.ClientConnectorError)

    def __init__(self, phoneIP: str, phonePort: int):
        self.ip = phoneIP
        self.port = phonePort
        self.baseAddress = f"http://{self.ip}:{self.port}"
        self.isAlive = True
        self.config = {}
        self.dataBuffer: List[DataFrame] = list()
        self.dataChannels: List[str] = list()
        self.allChannelsReq: str = ""
        self.startAt = 0
        self.endAt = 0
        self.deltaTime = 0

        self._didLastRequestFailed = False
        self._internalClock = 0

    def didLastRequestFailed(self) -> bool:
        tmp = self._didLastRequestFailed
        self._didLastRequestFailed = False
        return tmp

    async def ping(self) -> None:
        async with aiohttp.ClientSession() as client:
            try:
                response = await client.get(self.baseAddress)
                self.isAlive = response.ok
                response.close()
            except PhyphoxPhone.CONNECTION_ERROR:
                self.isAlive = False

    async def getRemoteConfig(self) -> None:
        async with aiohttp.ClientSession() as client:
            try:
                async with client.get(f"{self.baseAddress}/config") as response:
                    if response.status != 200:
                        self._didLastRequestFailed = True
                        return
                    self.config = await response.json()
                    self.dataChannels.clear()
                    for inp in self.config["inputs"]:
                        for channel in inp["outputs"]:
                            self.dataChannels.extend(channel.values())
                    self.allChannelsReq = "&".join(self.dataChannels)
            except PhyphoxPhone.CONNECTION_ERROR:
                self._didLastRequestFailed = True

    async def startExperiment(self) -> None:
        async with aiohttp.ClientSession() as client:
            try:
                async with client.get(f"{self.baseAddress}/control?cmd=start") as response:
                    if response.status != 200:
                        self._didLastRequestFailed = True
                        return
                    self.startAt = time.time_ns()
            except PhyphoxPhone.CONNECTION_ERROR:
                self._didLastRequestFailed = True

    async def stopExperiment(self) -> None:
        async with aiohttp.ClientSession() as client:
            try:
                async with client.get(f"{self.baseAddress}/control?cmd=stop") as response:
                    if response.status != 200:
                        self._didLastRequestFailed = True
                        return
                    self.endAt = time.time_ns()
            except PhyphoxPhone.CONNECTION_ERROR:
                self._didLastRequestFailed = True

    async def resetExperiment(self) -> None:
        self.dataBuffer.clear()
        self.startAt = self.endAt = self._internalClock = 0

        async with aiohttp.ClientSession() as client:
            try:
                async with client.get(f"{self.baseAddress}/control?cmd=clear") as response:
                    if response.status != 200:
                        self._didLastRequestFailed = True
                    response.close()
            except PhyphoxPhone.CONNECTION_ERROR:
                self._didLastRequestFailed = True

    async def getRemoteTime(self) -> dict or None:
        async with aiohttp.ClientSession() as client:
            try:
                async with client.get(f"{self.baseAddress}/time") as response:
                    if response.status != 200:
                        raise ConnectionError
                    return await response.json()
            except PhyphoxPhone.CONNECTION_ERROR as e:
                self._didLastRequestFailed = True
                return None

    async def getCurrentData(self, frameRate: float):
        async with aiohttp.ClientSession() as client:
            try:
                async with client.get(f"{self.baseAddress}/get?{self.allChannelsReq}") as response:
                    if response.status != 200:
                        raise ConnectionError
                    result = await response.json()
                    self.dataBuffer.append(DataFrame(self._internalClock, {channel: result["buffer"][channel]["buffer"][0] for channel in self.dataChannels}))
                    self._internalClock += frameRate
            except PhyphoxPhone.CONNECTION_ERROR:
                self._didLastRequestFailed = True
                self.dataBuffer.append(DataFrame(self._internalClock, None))
                self._internalClock += frameRate
                return

    async def getDataByHand(self, *args):
        async with aiohttp.ClientSession() as client:
            try:
                async with client.get(f"{self.baseAddress}/get?{'&'.join(args)}") as response:
                    if response != 200:
                        raise ConnectionError
                    return response.json()
            except PhyphoxPhone.CONNECTION_ERROR:
                self._didLastRequestFailed = True
                return None
