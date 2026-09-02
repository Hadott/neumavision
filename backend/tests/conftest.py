import os
import sys
from pathlib import Path


TEST_ROOT = Path(__file__).parent / ".test-data"
TEST_ROOT.mkdir(parents=True, exist_ok=True)
TEST_DATABASE = TEST_ROOT / "test.db"
TEST_DATABASE.unlink(missing_ok=True)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DATABASE}"
os.environ["UPLOAD_DIR"] = str(TEST_ROOT / "uploads")
os.environ["DETECTOR_MODE"] = "mock"
