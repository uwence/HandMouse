import tempfile
import os
import pytest
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
from handmouse.config.schema import dict_to_app_config


def test_load_nonexistent_config_creates_default() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = os.path.join(tmpdir, "config.yaml")
        
        # Load nonexistent config
        config = load_or_create_config(config_file)
        
        # Verify it returns default config and creates the file
        assert config == DEFAULT_CONFIG
        assert os.path.exists(config_file)


def test_save_and_load_config() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = os.path.join(tmpdir, "config.yaml")
        
        custom_config = AppConfig(
            camera=CameraConfig(width=1280, height=720, index=2, buffer_size=2, fps_target=30),
            pointer=PointerConfig(
                control_region=ControlRegion(left=0.2, top=0.2, right=0.8, bottom=0.8),
                g_hi=5.0,
            ),
            shortcut=ShortcutConfig(min_distance=0.25, max_duration_ms=800, cooldown_ms=600, axis_ratio=1.5),
            clutch=ClutchConfig(key_name="alt_l"),
            gesture_switches=GestureSwitches(right_click=False, double_click=True, drag_drop=False, alt_tab=True, win_d=False),
            gesture_config=ExtendedGestureConfig(pinch_close_ratio=0.4, pinch_open_ratio=0.6),
            grab_scroll_config=ExtendedGrabScrollConfig(scroll_sensitivity=120.0),
        )
        
        save_config(custom_config, config_file)
        loaded = load_or_create_config(config_file)
        
        assert loaded == custom_config


def test_load_corrupt_config_returns_default() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = os.path.join(tmpdir, "config.yaml")
        with open(config_file, "w") as f:
            f.write("[invalid yaml")
            
        config = load_or_create_config(config_file)
        assert config == DEFAULT_CONFIG


def test_config_schema_version_defaults_to_v2() -> None:
    config = dict_to_app_config({})
    assert config.schema_version == 2
    assert config.gesture_switches.win_d is False


def test_invalid_high_risk_cooldown_is_rejected() -> None:
    with pytest.raises(ValueError):
        dict_to_app_config({"policy": {"high_risk_cooldown_ms": -1}})


def test_bimanual_config_defaults():
    from handmouse.config import AppConfig, DEFAULT_CONFIG
    assert hasattr(DEFAULT_CONFIG, "bimanual")
    assert DEFAULT_CONFIG.bimanual.enabled is False
    assert DEFAULT_CONFIG.bimanual.dominant_hand == "right"


def test_bimanual_config_parses_from_dict():
    from handmouse.config.schema import dict_to_app_config
    d = {
        "schema_version": 2,
        "camera": {"width": 640, "height": 480, "index": 0},
        "pointer": {"control_region": {"left": 0.1, "top": 0.1, "right": 0.9, "bottom": 0.9}},
        "shortcut": {"min_distance": 0.18, "max_duration_ms": 900, "cooldown_ms": 700, "axis_ratio": 1.4},
        "clutch": {"key_name": "ctrl_r"},
        "bimanual": {
            "enabled": True,
            "dominant_hand": "left",
            "open_hold_ms": 300,
            "suspend_grace_ms": 200,
            "idle_grace_ms": 600,
        },
    }
    config = dict_to_app_config(d)
    assert config.bimanual.enabled is True
    assert config.bimanual.dominant_hand == "left"
    assert config.bimanual.open_hold_ms == 300


def test_bimanual_config_invalid_dominant_hand_raises():
    from handmouse.config.schema import dict_to_app_config
    d = {
        "schema_version": 2,
        "camera": {"width": 640, "height": 480, "index": 0},
        "pointer": {"control_region": {"left": 0.1, "top": 0.1, "right": 0.9, "bottom": 0.9}},
        "shortcut": {"min_distance": 0.18, "max_duration_ms": 900, "cooldown_ms": 700, "axis_ratio": 1.4},
        "clutch": {"key_name": "ctrl_r"},
        "bimanual": {"dominant_hand": "center"},
    }
    with pytest.raises(ValueError, match="dominant_hand"):
        dict_to_app_config(d)


def test_bimanual_config_negative_open_hold_ms_raises():
    from handmouse.config.schema import dict_to_app_config
    d = {
        "schema_version": 2,
        "camera": {"width": 640, "height": 480, "index": 0},
        "pointer": {"control_region": {"left": 0.1, "top": 0.1, "right": 0.9, "bottom": 0.9}},
        "shortcut": {"min_distance": 0.18, "max_duration_ms": 900, "cooldown_ms": 700, "axis_ratio": 1.4},
        "clutch": {"key_name": "ctrl_r"},
        "bimanual": {"open_hold_ms": -1},
    }
    with pytest.raises(ValueError, match="open_hold_ms"):
        dict_to_app_config(d)
