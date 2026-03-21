import paho.mqtt.client as mqtt

client = mqtt.Client()

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("MQTT connected successfully")
    else:
        print(f"MQTT connect failed: {rc}")

client.on_connect = on_connect

client.connect("192.168.50.22", 1883, 60)
client.loop_forever()
