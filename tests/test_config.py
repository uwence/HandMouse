import tempfile
import os
from handmouse.config import (
    DEFAULT_CONFIG,
    AppConfig,
    CameraConfig,
    PointerConfig,
    ControlRegion,
    ShortcutConfig,
    ClutchConfig,
    GestureSwitches,
    ExtendedGestureConfig,
    ExtendedGrabScrollConfig,
    load_or_create_config,
    save_config,
)


def test_load_nonexistent_config_creates_default() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = os.path.join(tmpdir, "config.json")
        
        # Load nonexistent config
        config = load_or_create_config(config_file)
        
        # Verify it returns default config and creates the file
        assert config == DEFAULT_CONFIG
        assert os.path.exists(config_file)


def test_save_and_load_config() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = os.path.join(tmpdir, "config.json")
        
        custom_config = AppConfig(
            camera=CameraConfig(width=1280, height=720, index=2, buffer_size=2, fps_target=30),
            pointer=PointerConfig(
                control_region=ControlRegion(left=0.2, top=0.2, right=0.8, bottom=0.8),
                g_hi=5.0,
            ),
            shortcut=ShortcutConfig(min_distance=0.25, max_duration_ms=800, cooldown_ms=600, axis_ratio=1.5),
            clutch=ClutchConfig(key_name="alt_l"),
            gesture_switches=GestureSwitches(right_click=False, double_click=True, drag_drop=False, alt_tab=True, win_d=False),
            gesture_config=ExtendedGestureConfig(pinch_close=0.04, pinch_open=0.06),
            grab_scroll_config=ExtendedGrabScrollConfig(scroll_sensitivity=120.0),
        )
        
        save_config(custom_config, config_file)
        loaded = load_or_create_config(config_file)
        
        assert loaded == custom_config


def test_load_corrupt_config_returns_default() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = os.path.join(tmpdir, "config.json")
        with open(config_file, "w") as f:
            f.write("{invalid json")
            
        config = load_or_create_config(config_file)
        assert config == DEFAULT_CONFIG
