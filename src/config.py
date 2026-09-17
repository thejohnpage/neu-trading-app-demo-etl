from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    oltp_dsn: str = os.getenv("OLTP_DSN", "postgresql://trading_demo:trading_demo_change_me@host.docker.internal:5432/trading_demo")
    warehouse_dsn: str = os.getenv("WAREHOUSE_DSN", "postgresql://trading_dw:trading_dw_change_me@localhost:55433/trading_dw")
    interval_seconds: int = int(os.getenv("ETL_INTERVAL_SECONDS", "60"))
    batch_size: int = int(os.getenv("ETL_BATCH_SIZE", "500"))

settings = Settings()
