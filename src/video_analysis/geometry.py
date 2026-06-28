"""Spatial geometry helpers used by the analyzer."""
import math
from typing import Dict, List


def bbox_label_anchor(bbox: List[float]):
    x1, y1, _, _ = bbox
    return int(x1), max(18, int(y1) - 8)


def bbox_anchors(bbox: List[float]) -> Dict[str, tuple]:
    x1, y1, x2, y2 = bbox
    return {
        "center": ((x1 + x2) / 2.0, (y1 + y2) / 2.0),
        "bottom_center": ((x1 + x2) / 2.0, y2),
    }


def bbox_intersection_area(first: List[float], second: List[float]) -> float:
    ax1, ay1, ax2, ay2 = first
    bx1, by1, bx2, by2 = second
    width = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    height = max(0.0, min(ay2, by2) - max(ay1, by1))
    return width * height


def bbox_area(bbox: List[float]) -> float:
    x1, y1, x2, y2 = bbox
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def point_in_polygon(point, polygon: List[List[float]]) -> bool:
    if len(polygon) < 3:
        return False
    x, y = point
    inside = False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        intersects = ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def point_segment_distance(point, start, end) -> float:
    px, py = point
    sx, sy = start
    ex, ey = end
    dx = ex - sx
    dy = ey - sy
    denom = (dx * dx) + (dy * dy)
    if denom <= 1e-9:
        return math.hypot(px - sx, py - sy)
    t = max(0.0, min(1.0, ((px - sx) * dx + (py - sy) * dy) / denom))
    closest = (sx + (t * dx), sy + (t * dy))
    return math.hypot(px - closest[0], py - closest[1])


def point_polygon_distance(point, polygon: List[List[float]]) -> float:
    if point_in_polygon(point, polygon):
        return 0.0
    if not polygon:
        return float("inf")
    return min(
        point_segment_distance(
            point,
            (float(start[0]), float(start[1])),
            (float(polygon[(index + 1) % len(polygon)][0]), float(polygon[(index + 1) % len(polygon)][1])),
        )
        for index, start in enumerate(polygon)
    )
