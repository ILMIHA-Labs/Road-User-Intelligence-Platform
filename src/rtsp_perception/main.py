import argparse
import logging
import cv2
import time
import threading
from rtsp_ingestion import RTSPIngestion
from config_loader import load_cameras

# Import shared detection and publisher from edge_vision
from shared_modules import EdgeDetector, MQTTPublisher

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("RTSPPerception")

def process_stream(camera_config, broker_host, broker_port, show_video):
    camera_id = camera_config.get("id")
    ingestion = RTSPIngestion(camera_config)
    detector = EdgeDetector()
    publisher = MQTTPublisher(broker_host=broker_host, broker_port=broker_port, topic="camera/detections")
    
    if not ingestion.connect():
        logger.error(f"Camera {camera_id} failing to start.")
        return

    publisher.connect()
    
    logger.info(f"Started processing thread for {camera_id}")
    try:
        while True:
            frame, frame_number = ingestion.read_frame()
            
            if frame is None:
                continue # Skipped frame or momentary drop
                
            results = detector.detect_and_track(frame)
            publisher.publish_detections(camera_id, frame_number, results)
            
            if show_video:
                annotated = results.plot()
                # Scale down for display if needed
                annotated = cv2.resize(annotated, (640, 480))
                cv2.imshow(f"Stream: {camera_id}", annotated)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

    except KeyboardInterrupt:
        logger.info(f"Stopping thread for {camera_id}")
    finally:
        ingestion.release()
        publisher.disconnect()
        if show_video:
             cv2.destroyWindow(f"Stream: {camera_id}")

def main():
    parser = argparse.ArgumentParser(description="RTSP Perception Agent")
    parser.add_argument("--config", type=str, default="../../config/cameras.yaml", help="Path to camera config")
    parser.add_argument("--broker", type=str, default="localhost", help="MQTT broker host")
    parser.add_argument("--port", type=int, default=1883, help="MQTT broker port")
    parser.add_argument("--show", action="store_true", help="Show video feeds")
    args = parser.parse_args()

    cameras = load_cameras(args.config)
    if not cameras:
        logger.error("No cameras configured. Exiting.")
        return
        
    logger.info(f"Loaded {len(cameras)} cameras from config. Starting threads...")
    
    threads = []
    for cam in cameras:
        # For PyTorch/YOLO inference it's often better to use multiprocessing if CPU bound,
        # but threading works okay for MVP testing if GIL isn't the primary bottleneck
        # or if we are utilizing a fast GPU that handles the CUDA calls outside the GIL.
        t = threading.Thread(target=process_stream, args=(cam, args.broker, args.port, args.show))
        t.daemon = True
        t.start()
        threads.append(t)
        
    try:
        # Keep main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Platform shutting down.")
        
if __name__ == "__main__":
    main()
