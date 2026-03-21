import sys
from time import sleep
from gpiozero import AngularServo

# --- 參數定義 (Definitions) ---

# GPIO 腳位定義 (使用 BCM 編號)
# 對應 Raspberry Pi Zero 2W 的實體 Pin 12 (GPIO 18)
SERVO_PIN = 18

# 伺服馬達脈衝寬度設定 (Pulse Width Settings)
# 單位：秒 (seconds)
# 定義：SG90 的控制訊號範圍通常為 0.5ms (0度) 至 2.5ms (180度)
MIN_PULSE_WIDTH = 0.0005
MAX_PULSE_WIDTH = 0.0025

# 角度範圍定義
MIN_ANGLE = 0
MAX_ANGLE = 180

# --- 初始化 Pin Factory (硬體介面設定) ---

factory = None

try:
    # 嘗試匯入並使用 pigpio 工廠 (高穩定性，推薦)
    # 條件：需先安裝 pigpio 並執行 'sudo pigpiod'
    from gpiozero.pins.pigpio import PiGPIOFactory
    factory = PiGPIOFactory()
    print("[系統資訊] 成功啟用 pigpio 硬體定時模式。")
    
except (ImportError, OSError) as e:
    # 若失敗，則使用系統預設工廠
    print(f"[系統警告] 無法載入 pigpio: {e}")
    print("[系統資訊] 將使用預設軟體模式。")
    factory = None

# --- 初始化伺服馬達物件 ---

servo = AngularServo(
    SERVO_PIN,
    min_angle=MIN_ANGLE,
    max_angle=MAX_ANGLE,
    min_pulse_width=MIN_PULSE_WIDTH,
    max_pulse_width=MAX_PULSE_WIDTH,
    pin_factory=factory
)

def main():
    print(f"程式開始：控制 GPIO {SERVO_PIN}")
    print("按下 Ctrl+C 可中止程式")

    # 定義角度變數
    center_angle = 90

    try:
        # 步驟 1: 重製到 90 度 (Reset to Center)
        print(f"-> 重置: {center_angle} 度")
        servo.angle = center_angle
        sleep(1) # 停留 1 秒

    except KeyboardInterrupt:
        print("\n[使用者中斷] 程式停止中...")
    
    finally:
        # 清理資源
        # 將角度設為 None 以停止 PWM 訊號輸出
        servo.angle = None
        servo.close()
        print("[系統資訊] GPIO資源已釋放，程式結束。")

if __name__ == "__main__":
    main()