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
from gpiozero import AngularServo
from gpiozero.pins.pigpio import PiGPIOFactory

# ---------------- 1. 載入設定檔 ----------------
CONFIG_FILE = "config.json"

def load_config():
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(script_dir, CONFIG_FILE)
        with open(config_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"[FATAL] Config load error: {e}")
        sys.exit(1)

config = load_config()

# ---------------- 2. 參數初始化 ----------------
CAM_ID = config['device']['id']
IMG_FOLDER = config['device']['image_save_folder']

# Servo Params
SERVO_PIN = 18  # BCM Pin
CENTER_ANGLE = 85 # 歸零角度

# 從 Config 讀取角度設定
try:
    UP_ANGLE_OFFSET = config['servo']['up_angle']     # 例如 20
    DOWN_ANGLE_OFFSET = config['servo']['down_angle'] # 例如 20
    # 穩定時間: 移動到位後，等待多久才斷開訊號 + 拍照
    STABILIZE_TIME = config['servo']['stabilize_time']
    SHOT_COUNT = config['servo']['shot_count'] 
except KeyError:
    print("[WARN] Config 缺少伺服馬達參數，使用預設值")
    UP_ANGLE_OFFSET = 20
    DOWN_ANGLE_OFFSET = 20
    STABILIZE_TIME = 0.5
    SHOT_COUNT = 3
    print("[WARN] Config 缺少 shot_count，預設為 3 張")

# 脈衝寬度 (SG90 標準)
MIN_PULSE = 0.0005
MAX_PULSE = 0.0025

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

# ---------------- 3. 影像校正類別 (保持不變) ----------------
class ImageCalibrator:
    def __init__(self, npz_path, enable=True):
        self.enable = enable
        self.mtx = None
        self.dist = None
        self.new_camera_mtx = None
        self.roi = None
        self.last_dim = None

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
        if not self.enable:
            return img_path

        img = cv2.imread(img_path)
        if img is None:
            print(f"[ERROR] Could not read image: {img_path}")
            return img_path

        h, w = img.shape[:2]

        if self.last_dim != (w, h):
            self.new_camera_mtx, self.roi = cv2.getOptimalNewCameraMatrix(
                self.mtx, self.dist, (w, h), 1, (w, h)
            )
            self.last_dim = (w, h)

        undistorted = cv2.undistort(img, self.mtx, self.dist, None, self.new_camera_mtx)

        if CALIB_CROP and self.roi is not None:
            x, y, w_roi, h_roi = self.roi
            undistorted = undistorted[y:y+h_roi, x:x+w_roi]

        cv2.imwrite(img_path, undistorted)
        print(f"[CALIB] Corrected and saved: {img_path}")
        return img_path

calibrator = ImageCalibrator(CALIB_NPZ_PATH, enable=CALIB_ENABLE)

# ---------------- 4. 硬體設定 (Stable Servo) ----------------

# 強制檢查 pigpiod
try:
    factory = PiGPIOFactory()
    print("[INIT] 成功啟用 pigpio 硬體驅動。")
except OSError:
    print("[FATAL] 無法連接 pigpio daemon！請先執行 'sudo pigpiod'")
    sys.exit(1)

# 初始化 AngularServo
servo = AngularServo(
    SERVO_PIN,
    min_angle=0,
    max_angle=180,
    min_pulse_width=MIN_PULSE,
    max_pulse_width=MAX_PULSE,
    pin_factory=factory
)

# 紀錄當前角度 (初始為中心)
current_angle = CENTER_ANGLE

def move_servo_stable(target_angle):
    """
    穩定移動邏輯：
    1. 移動至目標角度
    2. 等待穩定 (STABILIZE_TIME)
    3. 斷開訊號 (Detach) 消除抖動
    """
    global current_angle
    
    # 邊界檢查
    target_angle = max(0, min(180, target_angle))
    
    print(f"[SERVO] 移動至 {target_angle} 度...", end="")
    servo.angle = target_angle
    
    # 等待馬達轉到定位並穩定下來
    # 這段時間同時也是給相機去震動的時間
    time.sleep(STABILIZE_TIME)
    
    # 斷開訊號 (重要！消除待機電流聲與微幅抖動)
    servo.angle = None
    
    current_angle = target_angle
    print(" -> 定位完成 (訊號已斷開)")

picam2 = Picamera2()

# ---------------- 5. 拍攝與流程 (核心修改) ----------------
def take_picture(label):
    date_str = datetime.now().strftime("%Y-%m-%d")
    folder_path = os.path.join(IMG_FOLDER, date_str)
    os.makedirs(folder_path, exist_ok=True)

    t0 = int(time.time())
    filename = f"{CAM_ID}_{label}_{t0}.jpg"
    filepath = os.path.join(folder_path, filename)

    try:
        t_start = time.time()
        picam2.capture_file(filepath)
        final_path = calibrator.process(filepath)
        t_total = time.time() - t_start
        print(f"[CAPTURE] Finished {label}: {t_total:.3f}s")
        return final_path
    except Exception as e:
        print(f"[ERROR] Take picture failed: {e}")
        return None

def send_all_images(file_list):
    valid_files = [f for f in file_list if f is not None]
    if not valid_files: 
        return

    total_shots = len(valid_files)
    DELIMITER_ID = b"::"
    DELIMITER_END = b"::END::"

    for i, fp in enumerate(valid_files):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((SERVER_IP, SERVER_PORT))
                
                # [關鍵修正] 修改通訊協定：格式為 "ID,總張數::"
                # 例如: "CAM01,2::"
                header_str = f"{CAM_ID},{total_shots}"
                s.sendall(header_str.encode("utf-8") + DELIMITER_ID)
                
                with open(fp, "rb") as f:
                    file_data = f.read()
                    s.sendall(file_data + DELIMITER_END)
                
                print(f"[SEND] Image {i+1}/{total_shots} sent: {os.path.basename(fp)}")
                time.sleep(0.5)
        except Exception as e:
            print(f"[ERROR] Failed to send image {os.path.basename(fp)}: {e}")

    print(f"[SEND] Completed.")

def run_capture_sequence():
    """
    根據 SHOT_COUNT 決定拍攝流程
    """
    print(f"[MISSION] Start Sequence (Mode: {SHOT_COUNT} shots)")
    image_files = []
    
    # 確保初始歸零
    move_servo_stable(CENTER_ANGLE)

    if SHOT_COUNT == 2:
        # --- 模式 A: 2張 (下 -> 上) ---
        # 1. 轉至俯角 (Down)
        target_down = CENTER_ANGLE + DOWN_ANGLE_OFFSET
        move_servo_stable(target_down)
        image_files.append(take_picture("down"))

        # 2. 轉至仰角 (Up) - 直接跳過中間
        target_up = CENTER_ANGLE - UP_ANGLE_OFFSET
        move_servo_stable(target_up)
        image_files.append(take_picture("up"))
        
        # 3. 復歸
        move_servo_stable(CENTER_ANGLE)

    else:
        # --- 模式 B: 3張 (下 -> 中 -> 上) ---
        # 1. 下
        target_down = CENTER_ANGLE + DOWN_ANGLE_OFFSET
        move_servo_stable(target_down)
        image_files.append(take_picture("down"))

        # 2. 中
        move_servo_stable(CENTER_ANGLE)
        image_files.append(take_picture("level"))

        # 3. 上
        target_up = CENTER_ANGLE - UP_ANGLE_OFFSET
        move_servo_stable(target_up)
        image_files.append(take_picture("up"))

        # 4. 復歸
        move_servo_stable(CENTER_ANGLE)

    # 傳送照片
    send_all_images(image_files)
    print("[MISSION] End Sequence")

# ---------------- 6. MQTT ----------------
def mqtt_capture_thread():
    # 啟動獨立執行緒進行拍照，避免卡住 MQTT Loop
    run_capture_sequence()

def on_message(client, userdata, msg):
    payload = msg.payload.decode("utf-8").strip()
    print(f"[MQTT] Received: {payload}")
    
    if payload.lower() == "capture":
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
        
        print("[SYSTEM] System Ready. Waiting for MQTT command 'capture'...")
        
        # 初始歸位
        move_servo_stable(CENTER_ANGLE)

        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n[SYSTEM] User interrupted.")
    except Exception as e:
        print(f"[ERROR] MQTT Loop error: {e}")
    finally:
        # 釋放資源
        servo.angle = None
        servo.close()
        client.publish(MQTT_TOPIC_STATUS, "offline", qos=1, retain=True)
        client.loop_stop()
        picam2.stop()
        print("[SYSTEM] Shutdown.")

if __name__ == "__main__":
    # 初始化相機
    picam2.configure(picam2.create_still_configuration())
    picam2.start()
    
    # 啟動主程式
    start_mqtt()