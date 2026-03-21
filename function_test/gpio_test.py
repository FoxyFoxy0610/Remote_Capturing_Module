import serial
import time
import sys
import termios
import tty

# 設定 UART
ser = serial.Serial(
    port='/dev/serial0',
    baudrate=115200,
    timeout=1
)

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
    """將資訊組合成指令並透過 UART 傳送"""
    cmd = f"{direction},{angle}\n"
    ser.write(cmd.encode())
    print(f"[SEND] {cmd.strip()}")

UP_ANGLE = 20
DOWN_ANGLE = 20

print("UART Servo Command Program")
print("Press 'u' to send UP command")
print("Press 'd' to send DOWN command")
print("Press 'q' to quit\n")

try:
    while True:
        key = get_key()

        if key == 'u':
            send_command("UP", UP_ANGLE)

        elif key == 'd':
            send_command("DOWN", DOWN_ANGLE)

        elif key == 'q':
            print("Exiting program...")
            break

except KeyboardInterrupt:
    pass

finally:
    ser.close()
    print("UART closed.")
