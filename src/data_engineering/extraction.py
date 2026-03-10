import sqlite3
import pandas as pd
import logging

logger = logging.getLogger(__name__)

class DataExtractor:
    """
    Extracts raw platform events from the Backend API database.
    """
    def __init__(self, db_path="road_user_platform.db"):
        self.db_path = db_path

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def extract_detections(self) -> pd.DataFrame:
        """Loads all detections into a DataFrame"""
        try:
            with self._get_connection() as conn:
                df = pd.read_sql_query("SELECT * FROM detections", conn)
            logger.info(f"Extracted {len(df)} rows from detections")
            return df
        except Exception as e:
            logger.error(f"Failed to extract detections: {e}")
            return pd.DataFrame()

    def extract_speeds(self) -> pd.DataFrame:
        """Loads all speeds into a DataFrame"""
        try:
            with self._get_connection() as conn:
                df = pd.read_sql_query("SELECT * FROM speeds", conn)
            logger.info(f"Extracted {len(df)} rows from speeds")
            return df
        except Exception as e:
            logger.error(f"Failed to extract speeds: {e}")
            return pd.DataFrame()

    def extract_violations(self) -> pd.DataFrame:
        """Loads all violations into a DataFrame"""
        try:
            with self._get_connection() as conn:
                df = pd.read_sql_query("SELECT * FROM violations", conn)
            logger.info(f"Extracted {len(df)} rows from violations")
            return df
        except Exception as e:
            logger.error(f"Failed to extract violations: {e}")
            return pd.DataFrame()
