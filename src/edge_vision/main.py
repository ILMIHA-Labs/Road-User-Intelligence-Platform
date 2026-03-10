import argparse
import logging
import cv2
import time
from camera_capture import CameraCapture
from detection import EdgeDetector
from publisher import MQTTPublisher

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("EdgeVisionMain")

def main():
    parser = argparse.ArgumentParser(description="Edge Vision Agent")
    parser.add_argument("--source", type=str, default="0", help="Camera source (index or file path)")
    parser.add_argument("--camera-id", type=str, default="edge_cam_01", help="Camera ID")
    parser.add_argument("--broker", type=str, default="localhost", help="MQTT broker host")
    parser.add_argument("--port", type=int, default=1883, help="MQTT broker port")
    parser.add_argument("--show", action="store_true", help="Show video feed")
    args = parser.parse_args()

    # Initialize components
    capture = CameraCapture(args.source)
    detector = EdgeDetector()
    publisher = MQTTPublisher(broker_host=args.broker, broker_port=args.port)

    if not capture.connect():
        logger.error("Exiting due to capture failure.")
        return

    # In a real edge scenario, if MQTT is down we might buffer, but for MVP we just connect
    publisher.connect()

    logger.info("Starting edge vision pipeline...")
    try:
        while True:
            start_time = time.time()
            frame, frame_number = capture.read_frame()
            
            if frame is None:
                break
                
            results, annotated_frame, counts = detector.detect_and_track(frame)
            published = publisher.publish_detections(args.camera_id, frame_number, results)
            
            fps = 1.0 / (time.time() - start_time)
            if frame_number % 30 == 0:
                 logger.info(f"Frame {frame_number}: Published {published} events. FPS: {fps:.1f}. Counts: {counts}")

            if args.show:
                # Resize for display if too large
                height, width = annotated_frame.shape[:2]
                if width > 1280:
                     annotated_frame = cv2.resize(annotated_frame, (1280, int(height * (1280/width))))
                cv2.imshow("Edge Vision with Counter", annotated_frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
    finally:
        capture.release()
        publisher.disconnect()
        cv2.destroyAllWindows()
        logger.info("Pipeline stopped.")

if __name__ == "__main__":
    main()
