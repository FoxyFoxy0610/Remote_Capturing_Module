import serial
import sys
import paho.mqtt.client as mqtt
import socket
import time
from picamera2 import Picamera2
import os
from datetime import datetime
import threading
import json
import cv2
import numpy as np

# ---------------- 1. 載入設定檔 ----------------
CONFIG_FILE = "config.json"

def load_config():
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"[FATAL] Config load error: {e}")
        sys.exit(1)

config = load_config()

# ---------------- 2. 參數初始化 ----------------
CAM_ID = config['device']['id']
IMG_FOLDER = config['device']['image_save_folder']

# Servo
SERVO_PORT = config['servo']['uart_port']
SERVO_BAUD = config['servo']['baudrate']
UP_ANGLE = config['servo']['up_angle']
DOWN_ANGLE = config['servo']['down_angle']
SERVO_DELAY = config['servo']['stabilize_time']

# MQTT & Server
MQTT_BROKER = config['mqtt']['broker_ip']
MQTT_PORT = config['mqtt']['port']
MQTT_TOPIC_CMD = config['mqtt']['topic_cmd']
MQTT_TOPIC_STATUS = f"{config['mqtt']['topic_status_prefix']}/{CAM_ID}/status"
SERVER_IP = config['server']['ip']
SERVER_PORT = config['server']['port']

# Calibration Params
CALIB_ENABLE = config['calibration']['enable']
CALIB_NPZ_PATH = config['calibration']['npz_file_path']
CALIB_CROP = config['calibration']['crop_roi']

# ---------------- 3. 影像校正類別 (優化版) ----------------
class ImageCalibrator:
    def __init__(self, npz_path, enable=True):
        self.enable = enable
        self.mtx = None
        self.dist = None
        self.new_camera_mtx = None
        self.roi = None
        self.last_dim = None # 用來快取影像尺寸

        if self.enable:
            self._load_params(npz_path)

    def _load_params(self, path):
        try:
            with np.load(path) as data:
                self.mtx = data['mtx']
                self.dist = data['dist']
            print(f"[CALIB] Loaded parameters from {path}")
        except Exception as e:
            print(f"[ERROR] Failed to load calibration file: {e}")
            print("[WARN] Calibration will be DISABLED for this session.")
            self.enable = False

    def process(self, img_path):
        """
        讀取圖片 -> 校正 -> 覆蓋存檔 -> 回傳路徑
        """
        if not self.enable:
            return img_path

        img = cv2.imread(img_path)
        if img is None:
            print(f"[ERROR] Could not read image for calibration: {img_path}")
            return img_path

        h, w = img.shape[:2]

        # 優化：如果圖片尺寸跟上次一樣，就不重複計算矩陣 (快取機制)
        if self.last_dim != (w, h):
            self.new_camera_mtx, self.roi = cv2.getOptimalNewCameraMatrix(
                self.mtx, self.dist, (w, h), 1, (w, h)
            )
            self.last_dim = (w, h)

        # 校正
        undistorted = cv2.undistort(img, self.mtx, self.dist, None, self.new_camera_mtx)

        # 裁切 (ROI)
        if CALIB_CROP and self.roi is not None:
            x, y, w_roi, h_roi = self.roi
            undistorted = undistorted[y:y+h_roi, x:x+w_roi]

        # 覆蓋原始檔案 (或你可以選擇另存 _calib.jpg)
        cv2.imwrite(img_path, undistorted)
        print(f"[CALIB] Corrected and saved: {img_path}")
        return img_path

# 初始化校正物件 (只會在程式啟動時跑一次，節省資源)
calibrator = ImageCalibrator(CALIB_NPZ_PATH, enable=CALIB_ENABLE)


# ---------------- 4. 硬體設定 (UART & Camera) ----------------
try:
    ser = serial.Serial(SERVO_PORT, SERVO_BAUD, timeout=1)
except Exception as e:
    print(f"[ERROR] UART Error: {e}")
    sys.exit(1)

def send_servo_cmd(direction, angle):
    cmd = f"{direction}{angle}\n"
    ser.write(cmd.encode())
    print(f"[SERVO] Sent: {cmd.strip()}")

picam2 = Picamera2()

# ---------------- 5. 拍攝與流程 ----------------
def take_picture(label):
    """
    拍照 -> (校正) -> 回傳路徑
    """
    date_str = datetime.now().strftime("%Y-%m-%d")
    folder_path = os.path.join(IMG_FOLDER, date_str)
    os.makedirs(folder_path, exist_ok=True)

    t0 = int(time.time())
    filename = f"{CAM_ID}_{label}_{t0}.jpg"
    filepath = os.path.join(folder_path, filename)

    try:
        # 1. 硬體拍照
        t_start = time.time()
        picam2.capture_file(filepath)
        
        # 2. 影像校正 (如果開啟)
        # 這裡會直接處理剛剛存好的檔案
        final_path = calibrator.process(filepath)
        
        t_total = time.time() - t_start
        print(f"[CAPTURE] Finished {label}: {t_total:.3f}s")
        return final_path

    except Exception as e:
        print(f"[ERROR] Take picture failed: {e}")
        return None

def send_all_images(file_list):
    """
    修正說明：
    改為「每張圖片建立一次獨立連線」，確保 Server 端能正確重置並接收下一張圖。
    """
    valid_files = [f for f in file_list if f is not None]
    if not valid_files: 
        return

    # 定義分隔符號
    DELIMITER_ID = b"::"
    DELIMITER_END = b"::END::"

    for i, fp in enumerate(valid_files):
        try:
            # 針對每一張圖片建立新的 Socket 連線
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((SERVER_IP, SERVER_PORT))
                
                # 傳送檔頭 (ID)
                # 註：若 Server 需要分辨是第幾張圖，建議在此處修改協議，例如傳送 ID_Index
                s.sendall(CAM_ID.encode("utf-8") + DELIMITER_ID)
                
                # 傳送圖片本體
                with open(fp, "rb") as f:
                    file_data = f.read()
                    s.sendall(file_data + DELIMITER_END)
                
                print(f"[SEND] Image {i+1}/{len(valid_files)} sent: {os.path.basename(fp)}")
                
                # 稍微等待，讓 Server 有時間處理並釋放資源 (非必要，但有助於穩定性)
                time.sleep(0.5)

        except Exception as e:
            print(f"[ERROR] Failed to send image {os.path.basename(fp)}: {e}")

    print(f"[SEND] Completed. Total sent: {len(valid_files)}")

def run_capture_sequence():
    print("[MISSION] Start")
    image_files = []

    # Step 1: Level
    image_files.append(take_picture("level"))

    # Step 2: Up
    send_servo_cmd("U", UP_ANGLE)
    time.sleep(SERVO_DELAY)
    image_files.append(take_picture("up"))

    # Return
    send_servo_cmd("D", UP_ANGLE)
    time.sleep(SERVO_DELAY)

    # Step 3: Down
    send_servo_cmd("D", DOWN_ANGLE)
    time.sleep(SERVO_DELAY)
    image_files.append(take_picture("down"))

    # Return
    send_servo_cmd("U", DOWN_ANGLE)
    time.sleep(SERVO_DELAY)

    # Send
    send_all_images(image_files)
    print("[MISSION] End")

# ---------------- 6. MQTT ----------------
def mqtt_capture_thread():
    run_capture_sequence()

def on_message(client, userdata, msg):
    payload = msg.payload.decode("utf-8").strip()
    if payload.lower() == "capture":
        print("[MQTT] Command: Capture")
        threading.Thread(target=mqtt_capture_thread, daemon=True).start()

def start_mqtt():
    client = mqtt.Client()
    client.will_set(MQTT_TOPIC_STATUS, "offline", qos=1, retain=True)
    client.on_message = on_message
    
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.publish(MQTT_TOPIC_STATUS, "online", qos=1, retain=True)
        client.subscribe(MQTT_TOPIC_CMD)
        client.loop_start()
        
        print("[SYSTEM] System Ready. Waiting for MQTT...")
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"[ERROR] MQTT Loop: {e}")
    finally:
        send_servo_cmd("R", DOWN_ANGLE)
        client.publish(MQTT_TOPIC_STATUS, "offline", qos=1, retain=True)
        client.loop_stop()
        picam2.stop()
        if ser.is_open: ser.close()
        print("[SYSTEM] Shutdown.")

if __name__ == "__main__":
    picam2.configure(picam2.create_still_configuration())
    picam2.start()
    start_mqtt()