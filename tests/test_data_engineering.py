import unittest
import os
import sys
import sqlite3

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from data_engineering.extraction import DataExtractor
from data_engineering.transformation import DataTransformer
from data_engineering.exporter import DataExporter

class TestDataEngineering(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        cls.test_db = "test_road_user_platform.db"
        cls.test_outdir = "test_analytics_out"
        
        # Create a mock SQLite DB
        conn = sqlite3.connect(cls.test_db)
        cursor = conn.cursor()
        
        # Detections
        cursor.execute('''CREATE TABLE detections (
                            id INTEGER PRIMARY KEY, camera_id TEXT, timestamp DATETIME, 
                            object_id INTEGER, class TEXT, helmet_status TEXT, 
                            bbox JSON, confidence REAL)''')
                            
        cursor.execute('''INSERT INTO detections (camera_id, timestamp, object_id, class, helmet_status, confidence)
                          VALUES ('cam1', '2023-10-27T10:00:00', 1, 'car', 'unknown', 0.9)''')
        cursor.execute('''INSERT INTO detections (camera_id, timestamp, object_id, class, helmet_status, confidence)
                          VALUES ('cam1', '2023-10-27T10:00:05', 1, 'car', 'unknown', 0.8)''') # User 1 later detection
        cursor.execute('''INSERT INTO detections (camera_id, timestamp, object_id, class, helmet_status, confidence)
                          VALUES ('cam1', '2023-10-27T10:01:00', 2, 'motorcycle', 'no_helmet', 0.95)''')                  

        # Speeds
        cursor.execute('''CREATE TABLE speeds (
                            id INTEGER PRIMARY KEY, camera_id TEXT, object_id INTEGER, 
                            speed_kmh REAL, timestamp DATETIME)''')
                            
        cursor.execute('''INSERT INTO speeds (camera_id, object_id, speed_kmh, timestamp)
                          VALUES ('cam1', 1, 50.5, '2023-10-27T10:00:00')''')
        cursor.execute('''INSERT INTO speeds (camera_id, object_id, speed_kmh, timestamp)
                          VALUES ('cam1', 1, 60.0, '2023-10-27T10:00:05')''') # User 1 max speed
        
        conn.commit()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.test_db):
            os.remove(cls.test_db)
        if os.path.exists(os.path.join(cls.test_outdir, "road_users_analytics.csv")):
            os.remove(os.path.join(cls.test_outdir, "road_users_analytics.csv"))
        if os.path.exists(cls.test_outdir):
             os.rmdir(cls.test_outdir)

    def test_extraction(self):
        extractor = DataExtractor(db_path=self.test_db)
        df_det = extractor.extract_detections()
        self.assertEqual(len(df_det), 3) # 3 raw detections

        df_speed = extractor.extract_speeds()
        self.assertEqual(len(df_speed), 2)

    def test_transformation(self):
        extractor = DataExtractor(db_path=self.test_db)
        df_det = extractor.extract_detections()
        df_speed = extractor.extract_speeds()
        
        transformer = DataTransformer()
        df_analytics = transformer.build_analytics_dataset(df_det, df_speed)
        
        # We should only have 2 unique road users (obj 1 and 2)
        self.assertEqual(len(df_analytics), 2)
        
        # User 1 should have grabbed the max speed of 60.0
        user1_row = df_analytics[df_analytics['object_id'] == 1].iloc[0]
        self.assertEqual(user1_row['speed_kmh'], 60.0)
        self.assertEqual(user1_row['class'], 'car')
        
        # User 2 had no speed recorded, should fill with 0.0
        user2_row = df_analytics[df_analytics['object_id'] == 2].iloc[0]
        self.assertEqual(user2_row['speed_kmh'], 0.0)

    def test_export(self):
        extractor = DataExtractor(db_path=self.test_db)
        transformer = DataTransformer()
        df_analytics = transformer.build_analytics_dataset(
             extractor.extract_detections(), extractor.extract_speeds())
             
        exporter = DataExporter(output_dir=self.test_outdir)
        exporter.export_csv(df_analytics, "road_users_analytics.csv")
        
        self.assertTrue(os.path.exists(os.path.join(self.test_outdir, "road_users_analytics.csv")))
        
if __name__ == '__main__':
    unittest.main()
