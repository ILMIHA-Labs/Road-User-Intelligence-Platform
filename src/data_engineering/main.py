import argparse
import logging
import time

from extraction import DataExtractor
from transformation import DataTransformer
from exporter import DataExporter

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("DataEngineeringETL")

def run_etl_pipeline(db_path, output_dir):
    """
    Orchestrates the Extraction -> Transformation -> Export pipeline.
    """
    logger.info("Starting Data Engineering ETL Pipeline...")
    
    extractor = DataExtractor(db_path=db_path)
    transformer = DataTransformer()
    exporter = DataExporter(output_dir=output_dir)
    
    # 1. Extraction
    df_detections = extractor.extract_detections()
    df_speeds = extractor.extract_speeds()
    df_violations = extractor.extract_violations()
    
    # 2. Transformation
    # Build a joined analytical view of road users and missing speeds
    df_analytics = transformer.build_analytics_dataset(df_detections, df_speeds)
    
    # Clean violations for direct dashboard counting
    df_violations = transformer.clean_timestamps(df_violations)
    
    # 3. Export
    if not df_analytics.empty:
        exporter.export_csv(df_analytics, "road_users_analytics.csv")
    
    if not df_violations.empty:
        exporter.export_csv(df_violations, "traffic_violations.csv")
        
    logger.info("ETL Pipeline completed successfully.")

def main():
    parser = argparse.ArgumentParser(description="Data Engineering ETL Process")
    parser.add_argument("--db", type=str, default="road_user_platform.db", help="Path to SQLite database")
    parser.add_argument("--outdir", type=str, default="data/analytics", help="Output directory for generated CSVs")
    parser.add_argument("--daemon", action="store_true", help="Run loop every 60 seconds instead of once")
    args = parser.parse_args()

    if args.daemon:
        logger.info("Running in daemon mode. Press Ctrl+C to stop.")
        try:
            while True:
                run_etl_pipeline(args.db, args.outdir)
                time.sleep(60)
        except KeyboardInterrupt:
             logger.info("Stopping Data Engineering Agent.")
    else:
        run_etl_pipeline(args.db, args.outdir)

if __name__ == "__main__":
    main()
