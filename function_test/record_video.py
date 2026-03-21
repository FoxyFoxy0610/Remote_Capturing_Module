# from picamera2 import Picamera2
# from libcamera import controls
# import time
# import cv2

# picam2 = Picamera2()

# video_config = picam2.create_video_configuration(
#     main={"size": (960, 720)},
#     controls={
#         "ExposureTime": 5000,         # unit: microseconds（μs）
#         "AnalogueGain": 0.0,          # ISO (4.0 ~ 12.0）
#     }
# )
# picam2.configure(video_config)

# frame_width = 960
# frame_height = 720
# fps = 30
# fourcc = cv2.VideoWriter_fourcc(*'mp4v')
# out = cv2.VideoWriter("./video_test.mp4", fourcc, fps, (frame_width, frame_height))

# try:
#     picam2.start()
#     time.sleep(1)
#     # picam2.start_and_record_video("video.mp4", duration=5)

#     while True:
#         start = time.time()
#         frame = picam2.capture_array()
#         frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
#         frame = cv2.resize(frame, (frame_width, frame_height))
#         out.write(frame)
#         print(time.time()-start, end='\r')
        
#         if cv2.waitKey(1) & 0xFF == ord('q'):
#             break

# except KeyboardInterrupt:
#     print("Exiting program...")

# finally:
#     # Release Webcam source
#     out.release()
#     cv2.destroyAllWindows()
#     print(f"Video recording finish!")

from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import FileOutput
import signal
import time

picam2 = Picamera2()

# 設定錄影解析度
video_config = picam2.create_video_configuration(
    main={"size": (1280, 720)},  # 你可改為 640x480
    controls={
        "ExposureTime": 5000,
        "AnalogueGain": 1.0,
    }
)
picam2.configure(video_config)

# H264 硬體編碼器
encoder = H264Encoder(bitrate=5000000)
output = FileOutput("hard_record.h264")

# 錄影中斷旗標
running = True

def handle_interrupt(sig, frame):
    global running
    running = False
    print("Stop signal received. Finishing recording...")

signal.signal(signal.SIGINT, handle_interrupt)

picam2.start()
picam2.start_recording(encoder, output)

print("Recording... Press Ctrl + C to stop.")

last_time = time.time()
frame_count = 0

try:
    while running:
        time.sleep(0.01)  # 小睡避免佔用 100% CPU

        # 計算 FPS
        frame_count += 1
        now = time.time()
        if now - last_time >= 1.0:
            print("FPS:", frame_count, end="\r")
            frame_count = 0
            last_time = now

except Exception as e:
    print("Error:", e)

finally:
    picam2.stop_recording()
    picam2.stop()
    print("Video saved to hard_record.h264")