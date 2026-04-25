"""
CameraManager — Gate G-02
§21 : camera.type · FakeCamera déterministe · PRODUCTION interdit · backend swappable
"""
from __future__ import annotations

import numpy as np
import pytest

from core.config_manager import ConfigManager
from core.exceptions import ConfigValidationError, CameraError
from camera.camera_manager import CameraBackend, CameraManager, RawFrame
from camera.fake_camera import FakeCamera, _build_frame


# ─────────────────────────────────────────────────────────────────────────────
#  Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _make_config(tmp_path, mode: str = "DEV", cam_type: str = "fake") -> ConfigManager:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        f"deployment_mode: {mode}\n"
        f"station_id: TEST-001\n"
        f"camera:\n"
        f"  type: {cam_type}\n"
        f"  fps: 5\n"
        f"  resolution:\n"
        f"    width: 1920\n"
        f"    height: 1080\n"
    )
    return ConfigManager(cfg_file).load()


@pytest.fixture
def dev_config(tmp_path):
    return _make_config(tmp_path, mode="DEV", cam_type="fake")


@pytest.fixture
def prod_config(tmp_path):
    return _make_config(tmp_path, mode="PRODUCTION", cam_type="fake")


@pytest.fixture
def fake_cam(dev_config):
    cam = FakeCamera(dev_config)
    cam.start()
    yield cam
    cam.stop()


# ─────────────────────────────────────────────────────────────────────────────
#  G-02-A  ConfigManager — GR-06 charge une fois
# ─────────────────────────────────────────────────────────────────────────────

class TestConfigManager:
    def test_load_once(self, tmp_path):
        cfg = _make_config(tmp_path)
        assert cfg.is_loaded

    def test_load_idempotent(self, tmp_path):
        cfg = _make_config(tmp_path)
        cfg.load()  # second appel — ne lève pas, ne recharge pas
        assert cfg.is_loaded

    def test_dot_notation_camera_type(self, dev_config):
        assert dev_config.get("camera.type") == "fake"

    def test_dot_notation_nested(self, dev_config):
        assert dev_config.get("camera.resolution.width") == 1920
        assert dev_config.get("camera.resolution.height") == 1080

    def test_dot_notation_default(self, dev_config):
        assert dev_config.get("nonexistent.key", "default") == "default"

    def test_dot_notation_missing_returns_none(self, dev_config):
        assert dev_config.get("camera.nonexistent") is None

    def test_deployment_mode_dev(self, dev_config):
        assert dev_config.deployment_mode == "DEV"

    def test_deployment_mode_production(self, prod_config):
        assert prod_config.deployment_mode == "PRODUCTION"

    def test_station_id(self, dev_config):
        assert dev_config.station_id == "TEST-001"

    def test_require_existing_key(self, dev_config):
        assert dev_config.require("camera.type") == "fake"

    def test_require_missing_raises(self, dev_config):
        with pytest.raises(KeyError):
            dev_config.require("nonexistent.deep.key")

    def test_file_not_found(self, tmp_path):
        cfg = ConfigManager(tmp_path / "nonexistent.yaml")
        with pytest.raises(FileNotFoundError):
            cfg.load()


# ─────────────────────────────────────────────────────────────────────────────
#  G-02-B  FakeCamera — frames déterministes
# ─────────────────────────────────────────────────────────────────────────────

class TestFakeCameraFrames:
    def test_frame_shape(self, fake_cam):
        f = fake_cam.grab_frame()
        assert f.image.shape == (1080, 1920, 3)

    def test_frame_dtype(self, fake_cam):
        f = fake_cam.grab_frame()
        assert f.image.dtype == np.uint8

    def test_frame_id_format(self, fake_cam):
        f = fake_cam.grab_frame()
        assert f.frame_id == "FAKE_000000"

    def test_frame_id_increments(self, fake_cam):
        f0 = fake_cam.grab_frame()
        f1 = fake_cam.grab_frame()
        assert f0.frame_id == "FAKE_000000"
        assert f1.frame_id == "FAKE_000001"

    def test_deterministic_same_n(self, dev_config):
        """Deux FakeCamera fraîches produisent la même frame 0."""
        cam1 = FakeCamera(dev_config)
        cam1.start()
        cam2 = FakeCamera(dev_config)
        cam2.start()

        f1 = cam1.grab_frame()
        f2 = cam2.grab_frame()

        np.testing.assert_array_equal(f1.image, f2.image)
        cam1.stop()
        cam2.stop()

    def test_deterministic_direct_build(self):
        """_build_frame(n) appelé 2× donne le même résultat."""
        img_a = _build_frame(5)
        img_b = _build_frame(5)
        np.testing.assert_array_equal(img_a, img_b)

    def test_different_frames_differ(self, dev_config):
        """Frame 0 ≠ frame 1 (bruit différent)."""
        cam = FakeCamera(dev_config)
        cam.start()
        f0 = cam.grab_frame()
        f1 = cam.grab_frame()
        assert not np.array_equal(f0.image, f1.image)
        cam.stop()

    def test_start_resets_counter(self, dev_config):
        """start() remet frame_count à 0 → même frame 0 qu'au premier start."""
        cam = FakeCamera(dev_config)
        cam.start()
        f_first = cam.grab_frame()
        cam.stop()

        cam.start()
        f_second = cam.grab_frame()

        np.testing.assert_array_equal(f_first.image, f_second.image)
        cam.stop()

    def test_timestamp_present(self, fake_cam):
        f = fake_cam.grab_frame()
        assert f.timestamp > 0.0

    def test_background_gray(self):
        """Pixels hors produit doivent être proches de 200."""
        img = _build_frame(0)
        # coin haut-gauche (hors tapis)
        corner = img[0:100, 0:100]
        mean = corner.mean()
        assert 196 <= mean <= 204, f"fond attendu ~200, obtenu {mean:.1f}"

    def test_product_area_darker(self):
        """Zone produit (tapis) doit être plus sombre que le fond."""
        img = _build_frame(0)
        bg_mean      = img[0:100, 0:100].mean()
        product_mean = img[400:500, 400:800].mean()
        assert product_mean < bg_mean

    def test_frame_count_property(self, fake_cam):
        assert fake_cam.frame_count == 0
        fake_cam.grab_frame()
        assert fake_cam.frame_count == 1

    def test_is_connected_after_start(self, fake_cam):
        assert fake_cam.is_connected() is True

    def test_is_connected_after_stop(self, dev_config):
        cam = FakeCamera(dev_config)
        cam.start()
        cam.stop()
        assert cam.is_connected() is False


# ─────────────────────────────────────────────────────────────────────────────
#  G-02-C  FakeCamera bloquée en PRODUCTION
# ─────────────────────────────────────────────────────────────────────────────

class TestFakeCameraProduction:
    def test_raises_config_validation_error(self, prod_config):
        with pytest.raises(ConfigValidationError, match="FORBIDDEN"):
            FakeCamera(prod_config)

    def test_error_is_config_validation_error(self, prod_config):
        """ConfigValidationError hérite de ValueError."""
        with pytest.raises(ValueError):
            FakeCamera(prod_config)

    def test_dev_mode_allowed(self, dev_config):
        cam = FakeCamera(dev_config)
        assert cam is not None


# ─────────────────────────────────────────────────────────────────────────────
#  G-02-D  CameraManager pluggable — backend swappable
# ─────────────────────────────────────────────────────────────────────────────

class _MockBackend(CameraBackend):
    """Backend factice pour tester le swapping."""

    def __init__(self) -> None:
        self.started  = False
        self.stopped  = False
        self._count   = 0

    def start(self)         -> None:    self.started = True
    def stop(self)          -> None:    self.stopped = True
    def is_connected(self)  -> bool:    return self.started
    def grab_frame(self)    -> RawFrame:
        import time
        img = np.zeros((1080, 1920, 3), dtype=np.uint8)
        self._count += 1
        return RawFrame(f"MOCK_{self._count:06d}", img, time.time())


class TestCameraManager:
    def test_fake_backend_loaded(self, dev_config):
        mgr = CameraManager(config=dev_config)
        assert isinstance(mgr.backend, FakeCamera)

    def test_unknown_type_raises(self, tmp_path):
        cfg = _make_config(tmp_path, cam_type="unknown_cam")
        with pytest.raises(ConfigValidationError):
            CameraManager(config=cfg)

    def test_inject_backend_directly(self):
        mock = _MockBackend()
        mgr  = CameraManager(backend=mock)
        assert mgr.backend is mock

    def test_backend_swappable(self):
        mock1 = _MockBackend()
        mock2 = _MockBackend()
        mgr   = CameraManager(backend=mock1)
        assert mgr.backend is mock1

        mgr.swap_backend(mock2)
        assert mgr.backend is mock2

    def test_no_config_no_backend_raises(self):
        with pytest.raises(ValueError):
            CameraManager()

    def test_manager_delegates_start(self):
        mock = _MockBackend()
        mgr  = CameraManager(backend=mock)
        mgr.start()
        assert mock.started is True

    def test_manager_delegates_stop(self):
        mock = _MockBackend()
        mgr  = CameraManager(backend=mock)
        mgr.stop()
        assert mock.stopped is True

    def test_manager_delegates_grab_frame(self):
        mock = _MockBackend()
        mgr  = CameraManager(backend=mock)
        f    = mgr.grab_frame()
        assert isinstance(f, RawFrame)
        assert f.frame_id == "MOCK_000001"

    def test_manager_is_connected(self):
        mock = _MockBackend()
        mgr  = CameraManager(backend=mock)
        assert mgr.is_connected() is False
        mgr.start()
        assert mgr.is_connected() is True

    def test_full_fake_pipeline(self, dev_config):
        """Cycle complet : CameraManager→FakeCamera→start→grab→stop."""
        mgr = CameraManager(config=dev_config)
        mgr.start()
        assert mgr.is_connected()

        f = mgr.grab_frame()
        assert f.image.shape == (1080, 1920, 3)
        assert f.frame_id    == "FAKE_000000"

        mgr.stop()
        assert not mgr.is_connected()

    def test_raw_frame_dataclass(self):
        import time
        img = np.zeros((10, 10, 3), dtype=np.uint8)
        f   = RawFrame("test_001", img, time.time())
        assert f.frame_id == "test_001"
        assert f.image    is img
