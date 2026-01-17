import RPi.GPIO as GPIO
import time
import subprocess
import os
from tflite_runtime.interpreter import Interpreter
from PIL import Image
import numpy as np

# GPIO Setup
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

# Pin Configuration
TRIG = 23
ECHO = 24
SERVO_PIN = 25  # GPIO pin connected to servo signal

GPIO.setup(TRIG, GPIO.OUT)
GPIO.setup(ECHO, GPIO.IN)
GPIO.setup(SERVO_PIN, GPIO.OUT)
pwm = GPIO.PWM(SERVO_PIN, 50)  # 50Hz good for servo
pwm.start(0)

# Configurations
DETECTION_DISTANCE = 15
CAMERA_DEVICE = "/dev/video0"
CAMERA_RESOLUTION = "640x480"
MODEL_PATH = "waste_classifier.tflite"  # Your ML model filename
INPUT_SIZE = (224, 224)  # Adjust based on your model

# Servo positions
SERVO_CENTER = 90      # Center/neutral position
SERVO_BIO = 0          # Left position for biodegradable
SERVO_NON_BIO = 180    # Right position for non-biodegradable

# Create directory for images
os.makedirs("captured_waste", exist_ok=True)

# Load TFLite Model
try:
    print("Loading ML model...")
    interpreter = Interpreter(model_path=MODEL_PATH)
    interpreter.allocate_tensors()
    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()
    MODEL_LOADED = True
    print("✓ TFLite Model loaded successfully")
except Exception as e:
    print(f"⚠️  Model loading failed: {e}")
    print("   Running in MOCK mode")
    MODEL_LOADED = False
    interpreter = None

def get_distance():
    GPIO.output(TRIG, False)
    time.sleep(0.1)
    GPIO.output(TRIG, True)
    time.sleep(0.00001)
    GPIO.output(TRIG, False)
    timeout = time.time() + 1
    pulse_start = time.time()
    while GPIO.input(ECHO) == 0 and time.time() < timeout:
        pulse_start = time.time()
    pulse_end = time.time()
    while GPIO.input(ECHO) == 1 and time.time() < timeout:
        pulse_end = time.time()
    pulse_duration = pulse_end - pulse_start
    distance = pulse_duration * 17150
    return round(distance, 2)

def capture_image(filename):
    filepath = os.path.join("captured_waste", filename)
    cmd = f"fswebcam --device {CAMERA_DEVICE} -r {CAMERA_RESOLUTION} --no-banner {filepath}"
    result = subprocess.run(cmd.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode == 0 and os.path.exists(filepath):
        return filepath
    return None

def classify_waste(image_path):
    if not MODEL_LOADED:
        import random
        time.sleep(0.3)
        return random.choice(["biodegradable", "non-biodegradable"])
    try:
        img = Image.open(image_path).convert('RGB')
        img = img.resize(INPUT_SIZE)
        img_array = np.array(img, dtype=np.float32) / 255.0
        img_array = np.expand_dims(img_array, axis=0)
        interpreter.set_tensor(input_details[0]['index'], img_array)
        interpreter.invoke()
        output = interpreter.get_tensor(output_details[0]['index'])
        prediction = output[0][0]
        return "biodegradable" if prediction > 0.5 else "non-biodegradable"
    except Exception as e:
        print(f"⚠️  Classification error: {e}")
        return "non-biodegradable"

def set_servo_angle(angle):
    duty = angle / 18 + 2.5  # Adjust duty to servo angle with offset
    pwm.ChangeDutyCycle(duty)
    time.sleep(0.5)  # Give servo time to reach position
    pwm.ChangeDutyCycle(0)

def operate_servo(classification):
    """Operate servo based on classification and return to center"""
    if classification == "biodegradable":
        print(f"Servo rotating to {SERVO_BIO}° (Biodegradable - LEFT)")
        set_servo_angle(SERVO_BIO)
        time.sleep(2)  # Wait 2 seconds for waste disposal
        print(f"Servo returning to center position ({SERVO_CENTER}°)")
        set_servo_angle(SERVO_CENTER)
    else:
        print(f"Servo rotating to {SERVO_NON_BIO}° (Non-Biodegradable - RIGHT)")
        set_servo_angle(SERVO_NON_BIO)
        time.sleep(2)  # Wait 2 seconds for waste disposal
        print(f"Servo returning to center position ({SERVO_CENTER}°)")
        set_servo_angle(SERVO_CENTER)

def main():
    print("=" * 70)
    print(" " * 15 + "SMART WASTE SEGREGATION BIN")
    print(" " * 20 + "(Fully Integrated Model)")
    print("=" * 70)
    print(f"\n📊 System Configuration:\n   • Ultrasonic Sensor on GPIO {TRIG}/{ECHO}\n   • Servo on GPIO {SERVO_PIN}\n   • Camera: {CAMERA_DEVICE} @ {CAMERA_RESOLUTION}\n   • TFLite Model: {MODEL_PATH} {'(Loaded)' if MODEL_LOADED else '(Mock Mode)'}\n   • Input Image Size: {INPUT_SIZE}\n   • Detection Distance Threshold: {DETECTION_DISTANCE} cm")
    print("=" * 70)
    
    # Initialize servo to center position
    print("Initializing servo to center position...")
    set_servo_angle(SERVO_CENTER)
    time.sleep(1)
    
    print("\nSystem running... Waiting for detection...\n")

    detection_count = 0
    bio_count = 0
    non_bio_count = 0

    try:
        while True:
            distance = get_distance()
            if distance < DETECTION_DISTANCE and distance > 2:
                detection_count += 1
                timestamp = int(time.time())
                print(f"\n{'=' * 70}\nDetection #{detection_count} at {time.strftime('%H:%M:%S')}\nDistance: {distance} cm")
                filename = f"waste_{timestamp}_{detection_count}.jpg"
                print("Capturing image...")
                image_path = capture_image(filename)
                if image_path:
                    print(f"Image captured: {filename}")
                    print("Classifying...")
                    start = time.time()
                    classification = classify_waste(image_path)
                    inference_time = time.time() - start
                    print(f"Result: {classification.upper()} (Inference: {inference_time:.2f}s)")
                    
                    if classification == "biodegradable":
                        bio_count += 1
                    else:
                        non_bio_count += 1
                    
                    # Operate servo - rotate, wait, return to center
                    operate_servo(classification)
                    
                    print(f"📈 Stats: Bio={bio_count} | Non-Bio={non_bio_count}")
                else:
                    print("Image capture failed; skipping classification.")
                print("=" * 70)
                time.sleep(2)
            time.sleep(0.2)

    except KeyboardInterrupt:
        print("\nSystem stopping...")
        print(f"Total detections: {detection_count}")
        if detection_count > 0:
            print(f"   Biodegradable: {bio_count} ({bio_count/detection_count*100:.1f}%)")
            print(f"   Non-Biodegradable: {non_bio_count} ({non_bio_count/detection_count*100:.1f}%)")
        print(f"Images captured: {len([f for f in os.listdir('captured_waste') if f.endswith('.jpg')])}")
    finally:
        # Return servo to center before cleanup
        print("Returning servo to center position...")
        set_servo_angle(SERVO_CENTER)
        time.sleep(0.5)
        pwm.stop()
        GPIO.cleanup()
        print("GPIO cleaned up, system stopped.")

if __name__ == "__main__":
    main()
