import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_BASE = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
OPENROUTER_EMAIL_MODEL = os.getenv("OPENROUTER_EMAIL_MODEL", OPENROUTER_MODEL)

AGENCY_NAME = "Upthrust"
AGENCY_SENDER = "Alex Rivera"
AGENCY_ROLE = "Partnerships"

SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER).strip()

LEADS_JSON = DATA_DIR / "leads.json"
LEADS_CSV = DATA_DIR / "leads.csv"
LEADS_XLSX = DATA_DIR / "leads.xlsx"
