import phyclient

client = phyclient.Phyclient(6060)
client.runListener()

while True:
    try:
        data = client.getData()
        print(data)
    except phyclient.PhyClosed:
        print("Experiment ended !")
        break
