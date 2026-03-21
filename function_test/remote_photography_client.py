import paho.mqtt.client as mqtt
import socket
import time
from picamera2 import Picamera2
import os
from datetime import datetime

# MQTT_BROKER = "192.168.50.22"
MQTT_BROKER = "10.238.180.144"
CAM_ID = "CAM01"
MQTT_TOPIC_CMD = f"camera/all/cmd"
MQTT_TOPIC_STATUS = f"camera/{CAM_ID}/status"

# SERVER_IP = "192.168.50.22"
SERVER_IP = "10.238.180.144"
SERVER_PORT = 8000

picam2 = Picamera2()
running = True

# Receive message for mission
def on_message(client, userdata, msg):
    payload = msg.payload.decode("utf-8").strip()
    print(f"[MQTT] Command received: {payload}")

    if payload.lower() == "capture":
        run_capture_sequence()

# Capture image, save as a file and send back to server
def run_capture_sequence():
    global picam2
    print("[CAPTURE] Command received")

    date_str = datetime.now().strftime("%Y-%m-%d")
    folder_path = os.path.join("images", date_str)
    os.makedirs(folder_path, exist_ok=True)

    t0 = int(time.time())
    filename = f"{CAM_ID}_{t0}.jpg"
    filepath = os.path.join(folder_path, filename)

    t_capture_start = time.time()
    picam2.capture_file(filepath)
    t_capture = time.time() - t_capture_start
    print(f"[CAPTURE] Photo saved: {filepath} ({t_capture:.3f}s)")

    t_send_start = time.time()
    send_image_via_socket(filepath)
    t_send = time.time() - t_send_start
    print(f"[SEND] Finished sending ({t_send:.3f}s)")

def send_image_via_socket(filepath):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((SERVER_IP, SERVER_PORT))
        s.sendall(CAM_ID.encode("utf-8") + b"::")

        with open(filepath, "rb") as f:
            s.sendall(f.read())

    print("[SEND] Image sent to server.")

# Start connet to MQTT
def start_mqtt():
    global running
    client = mqtt.Client()
    client.will_set(MQTT_TOPIC_STATUS, "offline", qos=1, retain=True)

    client.on_message = on_message
    client.connect(MQTT_BROKER, 1883, 60)

    client.publish(MQTT_TOPIC_STATUS, "online", qos=1, retain=True)

    client.subscribe(MQTT_TOPIC_CMD)
    print(f"[MQTT] Subscribed: {MQTT_TOPIC_CMD}")
    print(f"[MQTT] Status set to online")

    client.loop_start()

    try:
        while running:
            time.sleep(1)
    except KeyboardInterrupt:
        print("[SYSTEM] Shutting down...")
    finally:
        client.publish(MQTT_TOPIC_STATUS, "offline", qos=1, retain=True)
        client.loop_stop()
        picam2.stop()
        print("[SYSTEM] Client exited cleanly.")


if __name__ == "__main__":
    picam2.configure(picam2.create_still_configuration())
    picam2.start()
    print("[SYSTEM] Camera started and ready.")

    start_mqtt()