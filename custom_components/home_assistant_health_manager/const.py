from datetime import timedelta

DOMAIN = "home_assistant_health_manager"
PLATFORMS = ["sensor", "select", "text", "button"]
DEFAULT_NAME = "Home Assistant Health Manager"
UPDATE_INTERVAL = timedelta(minutes=15)
SCHEDULE_INTERVAL = timedelta(hours=1)
REPORT_DIR = "health_manager/reports"
STORE_VERSION = 1
STORE_KEY = f"{DOMAIN}_schedule"
