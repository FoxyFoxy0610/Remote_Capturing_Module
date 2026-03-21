import serial
import sys
import termios
import tty
import json
import os

# ---------------- 1. 載入設定檔 ----------------
CONFIG_FILE = "config.json"

def load_config():
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[ERROR] 找不到設定檔 {CONFIG_FILE}")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] 讀取設定檔失敗: {e}")
        sys.exit(1)

config = load_config()

# ---------------- 2. 從 Config 讀取參數 ----------------
SERVO_PORT = config['servo']['uart_port']
SERVO_BAUD = config['servo']['baudrate']

# 這裡直接讀取設定檔中的角度，方便您測試該角度是否合適
UP_ANGLE_VAL = config['servo']['up_angle']
DOWN_ANGLE_VAL = config['servo']['down_angle']

# ---------------- UART 設定 ----------------
try:
    ser = serial.Serial(
        port=SERVO_PORT,
        baudrate=SERVO_BAUD,
        timeout=1
    )
except Exception as e:
    print(f"[ERROR] 無法開啟 UART Port ({SERVO_PORT}): {e}")
    sys.exit(1)

def get_key():
    """以非阻塞方式讀取單一按鍵"""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        key = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return key

def send_command(direction, angle):
    """組合成單字母指令 + 角度"""
    cmd = f"{direction}{angle}\n"  # 例如 "U20\n"
    ser.write(cmd.encode())
    print(f"\r[SEND] {cmd.strip()}      ", end="") # \r 讓輸出版面乾淨一點

print(f"--- UART Servo Manual Control ---")
print(f"Target Port: {SERVO_PORT}")
print(f"Loaded Config Angles -> UP: {UP_ANGLE_VAL}, DOWN: {DOWN_ANGLE_VAL}")
print("---------------------------------")
print("Press 'u' : Send UP command (using config angle)")
print("Press 'd' : Send DOWN command (using config angle)")
print("Press 'q' : Quit")
print("---------------------------------")

try:
    while True:
        key = get_key()

        if key.lower() == 'u':
            send_command("U", UP_ANGLE_VAL)

        elif key.lower() == 'd':
            send_command("D", DOWN_ANGLE_VAL)

        elif key.lower() == 'q':
            print("\nExiting program...")
            break

except KeyboardInterrupt:
    print("\nInterrupted.")
    pass

finally:
    send_command("R", DOWN_ANGLE_VAL)
    if ser.is_open:
        ser.close()
    print("UART closed.")