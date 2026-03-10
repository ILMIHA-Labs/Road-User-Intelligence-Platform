import yaml
import logging

logger = logging.getLogger(__name__)

def load_cameras(config_path):
    """
    Loads camera configurations from a YAML file.
    """
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            return config.get('cameras', [])
    except Exception as e:
        logger.error(f"Error loading camera config from {config_path}: {e}")
        return []
