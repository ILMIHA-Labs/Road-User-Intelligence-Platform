import pandas as pd
import logging

logger = logging.getLogger(__name__)

class DataTransformer:
    """
    Cleans raw events and builds analytical features.
    """
    def __init__(self):
        pass

    def clean_timestamps(self, df: pd.DataFrame, col="timestamp") -> pd.DataFrame:
        """Ensures consistent datetime types."""
        if col in df.columns and not df.empty:
            df[col] = pd.to_datetime(df[col])
        return df

    def build_analytics_dataset(self, df_det: pd.DataFrame, df_speed: pd.DataFrame) -> pd.DataFrame:
        """
        Creates a flattened, joined dataset representing unique road users and 
        their terminal/average speed, ready for Analytics dashboards.
        """
        if df_det.empty:
             return pd.DataFrame()
             
        df_det = self.clean_timestamps(df_det)    
        df_speed = self.clean_timestamps(df_speed)
        
        # In a real scenario, an object_id is only unique per camera per session. 
        # For MVP, we group by camera_id + object_id to find the "active" footprint.
        
        # 1. Get the latest classification and helmet status for each object
        latest_detections = df_det.sort_values("timestamp").groupby(["camera_id", "object_id"]).last().reset_index()
        
        # 2. Get the maximum speed observed for each object
        if not df_speed.empty:
             max_speeds = df_speed.groupby(["camera_id", "object_id"])["speed_kmh"].max().reset_index()
        else:
             max_speeds = pd.DataFrame(columns=["camera_id", "object_id", "speed_kmh"])
             
        # 3. Join them
        analytics_df = pd.merge(latest_detections, max_speeds, on=["camera_id", "object_id"], how="left")
        
        # Fill missing speeds with 0
        analytics_df["speed_kmh"] = analytics_df["speed_kmh"].fillna(0.0)
        
        logger.info(f"Built analytics dataset with {len(analytics_df)} unique distinct road users")
        return analytics_df
        
    def aggregate_hourly(self, df: pd.DataFrame, time_col="timestamp") -> pd.DataFrame:
        """
        Aggregates a dataset into hourly buckets for time-series visualization.
        """
        if df.empty or time_col not in df.columns:
            return pd.DataFrame()
            
        df = df.copy()
        df.set_index(time_col, inplace=True)
        
        # Resample to 1 Hour and count occurrences, split by class
        hourly_counts = df.groupby('class_name').resample('1H').size().unstack(level=0, fill_value=0)
        
        return hourly_counts.reset_index()
