from pathlib import Path
from dotenv import load_dotenv
import os

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

LYZR_API_KEY: str | None = os.getenv("LYZR_API_KEY")

DATA_DIR = BASE_DIR / "data"
INFRA_STATE_PATH = DATA_DIR / "infrastructure_state.json"
RUNBOOKS_DIR = BASE_DIR / "runbooks"
