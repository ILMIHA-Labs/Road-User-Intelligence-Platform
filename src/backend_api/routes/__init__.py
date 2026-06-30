from .analytics import router as analytics_router
from .cameras import router as cameras_router
from .exports import router as exports_router
from .ingest import router as ingest_router
from .live import router as live_router
from .trends import router as trends_router
from .video_analysis import router as video_analysis_router
from .violations import router as violations_router

__all__ = [
    "analytics_router",
    "cameras_router",
    "exports_router",
    "ingest_router",
    "live_router",
    "trends_router",
    "video_analysis_router",
    "violations_router",
]
