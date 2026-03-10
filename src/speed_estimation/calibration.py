import logging

logger = logging.getLogger(__name__)

class CameraCalibration:
    """
    Handles converting tracking pixel coordinates to real-world meters.
    For the MVP, this uses a simplified scalar approach.
    """
    def __init__(self, pixels_per_meter=25.0):
        # 25 pixels = 1 meter is a completely arbitrary default for MVP
        self.pixels_per_meter = pixels_per_meter
        logger.info(f"Initialized CameraCalibration with {self.pixels_per_meter} pixels/meter")

    def pixels_to_meters(self, x, y):
        """
        Converts pixel coordinates to real-world meters.
        """
        return x / self.pixels_per_meter, y / self.pixels_per_meter

    def calculate_distance(self, pt1, pt2):
        """
        Calculates eukaryotic distance in meters between two pixel points.
        """
        m_x1, m_y1 = self.pixels_to_meters(*pt1)
        m_x2, m_y2 = self.pixels_to_meters(*pt2)
        
        distance = ((m_x2 - m_x1) ** 2 + (m_y2 - m_y1) ** 2) ** 0.5
        return distance
