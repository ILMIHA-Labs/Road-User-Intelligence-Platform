import os
import pandas as pd
import logging

logger = logging.getLogger(__name__)

class DataExporter:
    """
    Exports processed datasets to local storage (CSV/Parquet) for downstream systems (Phase 7 Analytics).
    """
    def __init__(self, output_dir="data/analytics"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def export_csv(self, df: pd.DataFrame, filename: str):
        """
        Exports DataFrame to Analytics directory as CSV.
        """
        if df.empty:
            logger.warning(f"No data to export for {filename}")
            return
            
        filepath = os.path.join(self.output_dir, filename)
        try:
            df.to_csv(filepath, index=False)
            logger.info(f"Successfully exported {len(df)} records to {filepath}")
        except Exception as e:
            logger.error(f"Failed to export {filename}: {e}")
