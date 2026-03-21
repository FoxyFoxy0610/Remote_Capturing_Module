import sys
import termios
import tty
import json
import os
from time import sleep
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
    except Exception:
        # 如果找不到設定檔，給予預設值以防程式崩潰
        return {"servo": {"up_angle": 20, "down_angle": 20}}

config_data = load_config()

# ---------------- 2. 參數設定 ----------------

SERVO_PIN = 18
CENTER_ANGLE = 85

# [關鍵參數 1] 穩定時間 (參考影片 1)
# 移動後要等待多久才切斷訊號？
# 太短：馬達還沒轉到就斷電 (位置不到位)
# 太長：馬達會開始出現電流聲
STABILIZE_DELAY = 0.5 

try:
    STEP_UP = config_data['servo']['up_angle']
    STEP_DOWN = config_data['servo']['down_angle']
except KeyError:
    STEP_UP = 20
    STEP_DOWN = 20

# [關鍵參數 2] 脈衝寬度 (參考影片 2)
# Lutz 的影片建議明確設定這兩個值
# 您的馬達如果轉不到 0 或 180，請微調這裡 (例如 0.0005 ~ 0.0024)
MIN_PULSE = 0.0005
MAX_PULSE = 0.0025

# ---------------- 3. 硬體初始化 (強制使用 pigpio) ----------------

# 影片 2 強調：必須使用 PiGPIOFactory 才能消除訊號抖動
# 請務必確認終端機已執行：sudo pigpiod
try:
    factory = PiGPIOFactory()
    print("[系統] 成功啟用 pigpio 硬體驅動 (Lutz 推薦模式)")
except OSError:
    print("[錯誤] 無法連接 pigpio daemon！")
    print("請先在終端機執行指令: sudo pigpiod")
    sys.exit(1)

servo = AngularServo(
    SERVO_PIN,
    min_angle=0,
    max_angle=180,
    min_pulse_width=MIN_PULSE,
    max_pulse_width=MAX_PULSE,
    pin_factory=factory
)

# 記錄當前角度
current_angle = CENTER_ANGLE

# ---------------- 4. 核心控制函式 (參考影片 1 邏輯) ----------------

def move_servo_stable(target_angle):
    """
    穩定移動函式：
    1. 給予角度指令 (Move)
    2. 等待馬達轉到定位 (Sleep)
    3. 停止發送訊號 (Detach) -> 這是消除待機抖動的關鍵
    """
    global current_angle
    
    # 邊界檢查
    target_angle = max(0, min(180, target_angle))
    
    # 1. 開始移動
    print(f"\r[移動] 轉向 {target_angle} 度...", end="")
    servo.angle = target_angle
    
    # 2. 等待到位 (Give it time to move)
    # 這段時間馬達是有力的 (Active Holding)
    sleep(STABILIZE_DELAY)
    
    # 3. 切斷訊號 (Detach / Signal Off)
    # 這是影片 1 提到的 "Stop sending signal"
    # 設為 None 後，馬達會放鬆，不再因為訊號微小波動而發抖
    servo.angle = None
    
    # 更新狀態
    current_angle = target_angle
    print(f" -> [定位] 訊號已切斷 (靜止)")

def move_step(direction_sign, step_value):
    target = current_angle + (direction_sign * step_value)
    move_servo_stable(target)

def return_to_home():
    print(f"\n[重置] 回歸原點 {CENTER_ANGLE} 度...")
    move_servo_stable(CENTER_ANGLE)

def get_key():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        key = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return key

# ---------------- 5. 主程式 ----------------

print(f"\n--- Servo Stable Controller (Youtube Logic) ---")
print(f"Pin: {SERVO_PIN} | Driver: pigpio")
print(f"Up Step: {STEP_UP} | Down Step: {STEP_DOWN}")
print("-----------------------------------------------")
print(f"Press 'u' : UP (往上轉)")
print(f"Press 'd' : DOWN (往下轉)")
print(f"Press 's' : Home (歸零)")
print(f"Press 'q' : Quit")
print("-----------------------------------------------")

try:
    # 啟動時先歸位
    move_servo_stable(CENTER_ANGLE)

    while True:
        key = get_key()

        if key.lower() == 'u':
            # 依據您的習慣：u 往負向
            move_step(-1, STEP_UP)

        elif key.lower() == 'd':
            # 依據您的習慣：d 往正向
            move_step(1, STEP_DOWN)
        
        elif key.lower() == 's':
            return_to_home()

        elif key.lower() == 'q':
            break

except KeyboardInterrupt:
    print("\n中斷")

finally:
    # 確保釋放資源
    servo.angle = None
    servo.close()
    print("資源已釋放")