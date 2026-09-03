import os
import sys
from pathlib import Path


TEST_ROOT = Path(__file__).parent / ".test-data"
TEST_ROOT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["UPLOAD_DIR"] = str(TEST_ROOT / "uploads")
os.environ["DETECTOR_MODE"] = "mock"
