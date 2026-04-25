"""tests.conftest — shared fixtures seed=42"""
import sys, os
import pytest
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def pytest_configure(config):
    np.random.seed(42)

@pytest.fixture(scope="session")
def synthetic_frame():
    rng = np.random.RandomState(42)
    frame = np.ones((1080, 1920, 3), dtype=np.uint8) * 200
    frame[340:740, 460:1460] = [180, 175, 170]
    frame[400:480, 550:730]  = [50, 100, 200]   # logo 1 bleu
    frame[600:660, 800:950]  = [50, 50, 180]    # logo 2 rouge
    noise = rng.normal(0, 5, frame.shape).astype(np.int16)
    return np.clip(frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)
