import os
import sys
from pathlib import Path


TEST_ROOT = Path(__file__).parent / ".test-data"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_ROOT / 'test.db'}"
os.environ["UPLOAD_DIR"] = str(TEST_ROOT / "uploads")
os.environ["DETECTOR_MODE"] = "mock"
