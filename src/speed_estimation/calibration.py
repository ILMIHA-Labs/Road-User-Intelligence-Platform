"""Camera calibration: convert tracking pixel coordinates to real-world metres.

Two calibration models are supported:

- **Homography** (recommended): a perspective transform built from >= 4
  correspondences between image points (pixels) and their real-world ground-plane
  coordinates (metres). This corrects perspective across the whole frame, so a
  distance or speed measured near the camera and far from it are both correct.
- **Scalar** `pixels_per_meter`: a single global scale. Simple but perspective-
  blind (distant objects move fewer pixels per metre than near ones), so it is
  only approximate. It can be derived from a single known real-world distance
  (`from_reference_distance`) which is far better than an arbitrary guess.

If nothing is provided the scale falls back to an arbitrary default and a warning
is recorded in :attr:`warnings` (surfaced in the analysis ``summary.json``).
"""
import logging
from typing import Any, List, Optional, Sequence, Tuple

from common.constants import DEFAULT_PIXELS_PER_METER

logger = logging.getLogger(__name__)

Point = Sequence[float]

SOURCE_HOMOGRAPHY = "homography"
SOURCE_REFERENCE_DISTANCE = "reference_distance"
SOURCE_SCALAR = "scalar"
SOURCE_SCALAR_DEFAULT = "scalar_default"


class CameraCalibration:
    """Converts pixel coordinates to real-world metres."""

    def __init__(
        self,
        pixels_per_meter: float = DEFAULT_PIXELS_PER_METER,
        homography: Optional[Any] = None,
        source: Optional[str] = None,
        warnings: Optional[List[str]] = None,
    ):
        self.pixels_per_meter = float(pixels_per_meter)
        self._homography = homography
        self.warnings: List[str] = list(warnings or [])
        if source is not None:
            self.source = source
        elif homography is not None:
            self.source = SOURCE_HOMOGRAPHY
        else:
            self.source = SOURCE_SCALAR
        logger.info("Initialized CameraCalibration (source=%s)", self.source)

    # ------------------------------------------------------------------
    # Constructors
    # ------------------------------------------------------------------
    @classmethod
    def default(cls) -> "CameraCalibration":
        """Arbitrary fallback scale — approximate; records a warning."""
        return cls(
            pixels_per_meter=DEFAULT_PIXELS_PER_METER,
            source=SOURCE_SCALAR_DEFAULT,
            warnings=[
                "No calibration provided; using an arbitrary default scale of "
                f"{DEFAULT_PIXELS_PER_METER} px/m. Speeds and distances are "
                "approximate. Provide a homography or a known reference distance."
            ],
        )

    @classmethod
    def from_reference_distance(
        cls,
        image_point_a: Point,
        image_point_b: Point,
        real_distance_m: float,
    ) -> "CameraCalibration":
        """Derive a scalar scale from two image points a known distance apart."""
        if real_distance_m <= 0:
            raise ValueError("real_distance_m must be positive")
        pixel_distance = _euclidean(image_point_a, image_point_b)
        if pixel_distance <= 0:
            raise ValueError("image points must be distinct")
        return cls(
            pixels_per_meter=pixel_distance / float(real_distance_m),
            source=SOURCE_REFERENCE_DISTANCE,
        )

    @classmethod
    def from_homography(
        cls,
        image_points: Sequence[Point],
        world_points_m: Sequence[Point],
    ) -> "CameraCalibration":
        """Build a homography from >= 4 image<->world (metres) correspondences."""
        if len(image_points) < 4 or len(world_points_m) < 4:
            raise ValueError("homography needs at least 4 point correspondences")
        if len(image_points) != len(world_points_m):
            raise ValueError("image_points and world_points_m must be the same length")
        import cv2
        import numpy as np

        src = np.asarray(image_points, dtype=np.float64)
        dst = np.asarray(world_points_m, dtype=np.float64)
        matrix, _ = cv2.findHomography(src, dst, method=0)
        if matrix is None:
            raise ValueError("could not compute a homography from the given points")
        return cls(homography=matrix, source=SOURCE_HOMOGRAPHY)

    @classmethod
    def from_config(cls, config: Optional[dict]) -> "CameraCalibration":
        """Build calibration from a config block, dispatching on its keys.

        Accepted shapes (checked in priority order):
          {"image_points": [...], "world_points_m": [...]}   -> homography
          {"reference": {"image_point_a", "image_point_b", "distance_m"}}
          {"pixels_per_meter": <float>}                       -> scalar
        Anything empty/invalid falls back to :meth:`default`.
        """
        if not config:
            return cls.default()
        try:
            if config.get("image_points") and config.get("world_points_m"):
                return cls.from_homography(config["image_points"], config["world_points_m"])
            reference = config.get("reference")
            if reference:
                return cls.from_reference_distance(
                    reference["image_point_a"],
                    reference["image_point_b"],
                    float(reference["distance_m"]),
                )
            if config.get("pixels_per_meter"):
                return cls(pixels_per_meter=float(config["pixels_per_meter"]), source=SOURCE_SCALAR)
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning("Invalid calibration config (%s); using default scale", exc)
            fallback = cls.default()
            fallback.warnings.append(f"Invalid calibration config ignored: {exc}")
            return fallback
        return cls.default()

    # ------------------------------------------------------------------
    # Conversion
    # ------------------------------------------------------------------
    def image_to_world(self, x: float, y: float) -> Tuple[float, float]:
        """Map a pixel coordinate to real-world metres on the ground plane."""
        if self._homography is not None:
            import cv2
            import numpy as np

            point = np.array([[[float(x), float(y)]]], dtype=np.float64)
            mapped = cv2.perspectiveTransform(point, self._homography)
            return float(mapped[0][0][0]), float(mapped[0][0][1])
        return x / self.pixels_per_meter, y / self.pixels_per_meter

    def pixels_to_meters(self, x: float, y: float) -> Tuple[float, float]:
        """Back-compatible scalar conversion (perspective-blind)."""
        return self.image_to_world(x, y)

    def calculate_distance(self, pt1: Point, pt2: Point) -> float:
        """Euclidean distance in metres between two pixel points."""
        m1 = self.image_to_world(pt1[0], pt1[1])
        m2 = self.image_to_world(pt2[0], pt2[1])
        return _euclidean(m1, m2)

    @property
    def has_homography(self) -> bool:
        return self._homography is not None

    def describe(self) -> dict:
        """Serializable calibration provenance for summary.json."""
        info: dict = {"source": self.source}
        if not self.has_homography:
            info["pixels_per_meter"] = round(self.pixels_per_meter, 4)
        if self.warnings:
            info["warnings"] = list(self.warnings)
        return info


def _euclidean(pt1: Point, pt2: Point) -> float:
    return ((pt2[0] - pt1[0]) ** 2 + (pt2[1] - pt1[1]) ** 2) ** 0.5
