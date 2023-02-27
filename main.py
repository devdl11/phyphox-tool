from rich.console import Console
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.progress import Progress
from rich.live import Live
from rich.table import Table

import asyncio
import multiprocessing
import signal
import threading


from typing import Type, List, Dict
from phyphox import PhyphoxPhone
import socket
import time
import json

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
doRunExperiment: bool = False
frameRate = 1/25
delayRequest = 0.03
requestTimeError = 0
packetsSent = 0


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
    global requestTimeError
    await device.resetExperiment()
    await device.startExperiment()
    await asyncio.sleep(2)
    await device.stopExperiment()
    await asyncio.sleep(delayRequest)
    remoteTime = await device.getRemoteTime()
    if remoteTime is None:
        return
    if len(remoteTime) < 2:
        device._didLastRequestFailed = True
        requestTimeError += 1
        return
    remoteStart = remoteEnd = 0
    for rem in remoteTime:
        if rem["event"] == "START":
            remoteStart = rem["experimentTime"]
        elif rem["event"] == "PAUSE":
            remoteEnd = rem["experimentTime"]
    remoteDelta = remoteEnd - remoteStart
    localDelta = (device.endAt - device.startAt) / 10**9 - delayRequest
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
    return requestTimeError <= len(phonesList) * 5 // 2


def dataServerLiveBroadcasting(output: multiprocessing.Queue):
    """
    This function must be run in a different thread in order to keep the interactive console.
    Here we broadcast the data gathered to a local port using the UDP protocol.
    The user can listen to the port to handle the data
    :return:
    """
    global packetsSent
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    console.print("[cyan] Broadcasting on", SERVER_PORT)
    while doRunExperiment or output.qsize() > 0:
        data = output.get()
        packet = {data[0]: data[1].toJson()}
        server.sendto(json.dumps(packet).encode(), ("127.0.0.1", SERVER_PORT))
        packetsSent += 1


def _errorBeforeLaunching() -> bool:
    for device in phonesList:
        if device.didLastRequestFailed():
            console.print(f"[red1] There is a problem with the device {device.ip} !")
            console.print("Please check the device before relaunching the experiment.")
            input("Continue...")
            return True
    return False


async def producerMinion(queue: multiprocessing.Queue, device: PhyphoxPhone):
    await device.getCurrentData(frameRate)
    queue.put((device.ip, device.dataBuffer[-1]))
    await asyncio.sleep(frameRate/device.deltaTime)


async def experimentProducer(output: multiprocessing.Queue, iinput: multiprocessing.Queue) -> None:
    await asyncio.gather(*(device.startExperiment() for device in phonesList))
    while True:
        await asyncio.gather(*(producerMinion(output, device) for device in phonesList))
        if iinput.qsize() > 0:
            if iinput.get():
                break
    await asyncio.gather(*(device.stopExperiment() for device in phonesList))
    await asyncio.sleep(delayRequest)
    await asyncio.gather(*(device.resetExperiment() for device in phonesList))


def experimentProducerProcessLauncher(output: multiprocessing.Queue, iinput: multiprocessing.Queue) -> None:
    """
    This function must be launched in a different process.
    It's used as a trampoline for the main function.
    :param iinput: Queue Main --> Process
    :param output: Queue Process --> Main
    :return: None
    """
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    asyncio.run(experimentProducer(output, iinput))


def generateExperimentStatusTable(queue: multiprocessing.Queue, startedAt: int):
    table = Table()
    table.add_row(f"Number of devices: {len(phonesList)}")
    table.add_row(f"Packets sent: {packetsSent}")
    table.add_row(f"In queue data: {queue.qsize()}")
    table.add_row(f"Server Port: {SERVER_PORT}")
    table.add_row()
    table.add_row(f"Experiment started {(time.time_ns() - startedAt)/10**9}s ago")
    table.add_row("Press CTRL-C to stop the experiment")
    return table

async def runExperiment() -> int:
    global frameRate, delayRequest, requestTimeError, doRunExperiment
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
        while True:
            res = await latencyPhone5Test()
            if not res:
                console.print("[red] Error: too many failures ! Increasing the delay threshold...")
                delayRequest += 0.01
                requestTimeError = 0
                continue
            console.print("[blue] -- Advance Latency Results :")
            for device in phonesList:
                console.print(" " * 2, "--", device.ip, " : ", device.deltaTime)
            break

    frameRate = 1 / IntPrompt.ask("How many data per second (frame rate) do you want ?", default=25)
    mainQueue = multiprocessing.Queue()
    commanderQueue = multiprocessing.Queue()
    doRunExperiment = True
    console.print("[italic] - Starting the experimentProducer process...")
    background_process = multiprocessing.Process(target=experimentProducerProcessLauncher, args=(mainQueue, commanderQueue,), daemon=True)
    background_process.start()
    console.print("[italic] - Waiting for the process...")
    mainQueue.get()
    started_at = time.time_ns()
    console.print("[italic] - Starting the broadcasting server...")
    server_thread = threading.Thread(target=dataServerLiveBroadcasting, args=(mainQueue, ), daemon=True)
    server_thread.start()
    with Live(generateExperimentStatusTable(mainQueue, started_at), refresh_per_second=5) as live:
        while doRunExperiment:
            try:
                live.update(generateExperimentStatusTable(mainQueue, started_at))

            except KeyboardInterrupt:
                console.print("[red] Interruption request detected !")
                doRunExperiment = False
    console.print("[italic] Noticing background service...")
    commanderQueue.put(True)
    console.print("[italic] Waiting for the server...")
    with Progress() as progress:
        maxSize = mainQueue.qsize()
        task = progress.add_task("[green] Dispatch remaining data...", total=maxSize)
        while mainQueue.qsize() > 0:
            delta = maxSize - mainQueue.qsize()
            maxSize = mainQueue.qsize()
            progress.update(task, advance=delta)
    console.print("[italic] Waiting for the background service to end...")
    background_process.join()
    console.print("[bold] All done !")
    input("Continue... ")
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
