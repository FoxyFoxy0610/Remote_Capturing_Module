from picamera2 import Picamera2
import time
import cv2

picam2 = Picamera2()

picam2.configure(picam2.create_still_configuration())

picam2.start()
time.sleep(0.2)

# frame = picam2.capture_array()
# frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
# cv2.imwrite("image_test.jpg", frame)

picam2.capture_file("image.jpg")

picam2.stop()