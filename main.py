from rich.console import Console
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.progress import Progress

import asyncio
import threading

from typing import Type, List, Dict
from phyphox import PhyphoxPhone
import socket
import time

### CONSTANT
PORT = 8080
SERVER_PORT = 6060

console = Console()
MY_IP: str = ""
LOCAL_NETWORK_IP: str = ""
MENU_POINTER: int = 0
doRun: bool = True
phonesList: List[PhyphoxPhone] = list()
alreadyPairedIps = set()
runExperiment: bool = False


def getLocalIp() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        res = s.getsockname()[0]
        s.close()
    except OSError:
        res = ""
    return res


def getEndpointFromIp(ip: str) -> int:
    return int(ip[ip.index(".", 3 * 2 + 2) + 1:])


def mainMenu() -> int:
    console.print("-" * 2, "MAIN", "-" * 2)
    console.print(" " * 2, "1 - Add a phone")
    console.print(" " * 2, "2 - Manage paired phones")
    console.print(" " * 2, "3 - Launch the experiment")
    console.print(" " * 2, "4 - Exit")

    subMenu = {
        1: 11,
        2: 12,
        3: 13,
        4: -1
    }

    choice = IntPrompt.ask("> ")
    if choice <= 0 or choice > 4:
        console.print("Incorrect Choice !")
        time.sleep(2)
        return 0
    return subMenu[choice]


def addPhone() -> int:
    global alreadyPairedIps, phonesList
    port = PORT
    console.print("-" * 2, "Phone Pairing", "-" * 2)
    console.print("Current Configuration: ")
    console.print(" " * 3, "PORT:", port)
    choice = Confirm.ask("Change configuration ?", default=False)
    if choice:
        port = IntPrompt.ask("> ")

    # ? Pre-allocate the list ?
    newPhones = list()
    newPhonesCount = 0

    with Progress() as progress:
        task = progress.add_task("[green] Scanning local network...", total=255)
        for endpoint in range(1, 255 + 1):
            if endpoint in alreadyPairedIps:
                continue
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.075)
                remoteIP = f"{LOCAL_NETWORK_IP}{endpoint}"
                s.connect((remoteIP, port))
                s.close()
                newPhones.append(endpoint)
                newPhonesCount += 1
            except (ConnectionError, OSError) as e:
                # Ignore... What can we do else ?
                pass
            progress.update(task, advance=1)

    console.print("[deep_sky_blue1] Phones detected:", newPhonesCount)
    if newPhonesCount == 0:
        input("Continue...")
        return 0

    console.print(" " * 3, "0 - Add all")
    for endpoint in range(newPhonesCount):
        console.print(" " * 3, f"{endpoint + 1} - Add {LOCAL_NETWORK_IP}{newPhones[endpoint]}")
    choice = IntPrompt.ask("> ")
    if choice < 0 or choice - 1 > newPhonesCount:
        console.print("[red] Invalid choice ! Dropping...")
        time.sleep(2)
        return 0
    if choice == 0:
        for endpoint in newPhones:
            phonesList.append(PhyphoxPhone(f"{LOCAL_NETWORK_IP}{endpoint}", port))
            alreadyPairedIps.add(endpoint)
        console.print(f"[green] Added [purple] {newPhonesCount} [green]phones !")
    else:
        phonesList.append(PhyphoxPhone(f"{LOCAL_NETWORK_IP}{newPhones[choice - 1]}", port))
        alreadyPairedIps.add(newPhones[choice - 1])
        console.print(f"[green] Added [purple] 1 [green]phone !")
    time.sleep(1)
    return 0


def pairedPhones() -> int:
    global phonesList, alreadyPairedIps
    console.print("-"*2, "PAIRED PHONES", "-"*2)
    numberOfPhones = len(phonesList)
    if numberOfPhones == 0:
        console.print("[red]No phone connected")
        input("Continue...")
        return 0
    console.print("Connected Phones: ")
    for i in range(numberOfPhones):
        console.print(" ", i + 1, ".", f"{phonesList[i].ip}:{phonesList[i].port}")
    console.print()
    console.print(" "*2, "0 - Do nothing")
    console.print(" "*2, "1 - Disconnect a phone")
    console.print(" "*2, "2 - Disconnect all phones")
    choice = IntPrompt.ask("> ")
    if not 0 <= choice <= 2:
        console.print("[red]Invalid choice !")
        time.sleep(2)
        return 0
    if choice == 2:
        phonesList.clear()
        alreadyPairedIps.clear()
        console.print("[green] All phones disconnected !")
        time.sleep(1)
    elif choice == 1:
        console.print("Select the phone:")
        for phoneI in range(numberOfPhones):
            console.print(" "*2, phoneI + 1, f". {phonesList[phoneI].ip}")
        choice = IntPrompt.ask("> ")
        if not 1 <= choice <= numberOfPhones:
            console.print("[red]Invalid choice !")
            time.sleep(2)
            return 0
        device = phonesList.pop(choice - 1)
        alreadyPairedIps.remove(getEndpointFromIp(device.ip))
        console.print(f"[green] Phone {device.ip} disconnected !")
        time.sleep(1)
    return 0


async def isPhyphoxPhoneAlive(device: PhyphoxPhone):
    global alreadyPairedIps, phonesList
    await device.ping()
    if not device.isAlive:
        console.print("[italic red] Phone", device.ip, "just died !")
        alreadyPairedIps.remove(getEndpointFromIp(device.ip))
        phonesList.remove(device)


async def deltaTimeTest(device: PhyphoxPhone):
    await device.resetExperiment()
    await device.startExperiment()
    await asyncio.sleep(2)
    await device.stopExperiment()
    await asyncio.sleep(0.01)
    remoteTime = await device.getRemoteTime()
    if remoteTime is None:
        return
    if len(remoteTime) < 2:
        device._didLastRequestFailed = True
        return
    remoteStart = remoteEnd = 0
    for rem in remoteTime:
        if rem["event"] == "START":
            remoteStart = rem["experimentTime"]
        elif rem["event"] == "PAUSE":
            remoteEnd = rem["experimentTime"]
    remoteDelta = remoteEnd - remoteStart
    localDelta = (device.endAt - device.startAt) / 10**9 - 0.01
    console.log(f"[italic]      {device.ip} - Remote : {remoteDelta} ; Local : {localDelta}")
    await device.resetExperiment()
    device.deltaTime = remoteDelta / localDelta


async def latencyPhone5Test():
    console.print("[italic] - Running 5 tests of latency per device...")
    latencyResults: Dict[str, List[float]] = {device.ip: list() for device in phonesList}
    for test in range(5):
        await asyncio.gather(*(deltaTimeTest(device) for device in phonesList))
        for device in phonesList:
            latencyResults[device.ip].append(device.deltaTime)
    for device in phonesList:
        device.deltaTime = sum(latencyResults[device.ip])/5
def dataServerLiveBroadcasting():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("0.0.0.0", SERVER_PORT))


def _errorBeforeLaunching() -> bool:
    for device in phonesList:
        if device.didLastRequestFailed():
            console.print(f"[red1] There is a problem with the device {device.ip} !")
            console.print("Please check the device before relaunching the experiment.")
            input("Continue...")
            return True
    return False


def experimentProducer(queue: asyncio.Queue) -> None:
    """
    This function must be launched in a different thread.
    Here we collect the data from the devices and push it into the Queue.
    :type queue: asyncio.Queue
    :return: None
    """

    pass


async def runExperiment() -> int:
    console.print("-"*2, "RUN EXPERIMENT", "-"*2)
    if len(phonesList) == 0:
        console.print("[red] Please connect a least one device to launch the experiment mode !")
        input("Continue...")
        return 0
    console.print("Before continuing, please be sure to have correctly configure your device.s")
    choice = Confirm.ask("Ready ? ", default=False)
    if not choice:
        return 0
    console.clear()
    console.print("[italic] - Retrieving configurations from devices...")
    await asyncio.gather(*(device.getRemoteConfig() for device in phonesList))
    if _errorBeforeLaunching():
        return 0
    console.print("[italic] - Running short test...")
    await asyncio.gather(*(deltaTimeTest(device) for device in phonesList))
    if _errorBeforeLaunching():
        return 0
    console.print("[blue] -- Latency Results :")
    for device in phonesList:
        console.print(" "*2, "--", device.ip, " : ", device.deltaTime)
    choice = Confirm.ask("Do you want to do more tests regarding the latency ?", default=False)
    if choice:
        await latencyPhone5Test()
        console.print("[blue] -- Advance Latency Results :")
        for device in phonesList:
            console.print(" " * 2, "--", device.ip, " : ", device.deltaTime)
    return 0


async def checkPhonesConnectivity():
    await asyncio.gather(*(isPhyphoxPhoneAlive(device) for device in phonesList))


async def main():
    global MY_IP, LOCAL_NETWORK_IP, MENU_POINTER, doRun
    console.print("=" * 5, "[red]PhyPhox console utility[white]", "=" * 5)
    # Let's get our ip
    MY_IP = getLocalIp()
    if len(MY_IP) < 3 * 2 + 2:
        console.print("[red3]Can't init: not connected to a local network !")
        return
    LOCAL_NETWORK_IP = MY_IP[:MY_IP.index(".", 3 * 2 + 2)] + "."
    console.print("[blue]COMPUTER IP:[white]", MY_IP)
    while doRun:
        if MENU_POINTER == 0:
            MENU_POINTER = mainMenu()
        elif MENU_POINTER == 11:
            MENU_POINTER = addPhone()
        elif MENU_POINTER == 12:
            MENU_POINTER = pairedPhones()
        elif MENU_POINTER == 13:
            MENU_POINTER = await runExperiment()
        doRun = MENU_POINTER != -1
        if doRun:
            console.clear()
        await checkPhonesConnectivity()

    console.print("[italic]Cleaning up...")
    console.print("[bold]Done.")


if __name__ == "__main__":
    asyncio.run(main())
