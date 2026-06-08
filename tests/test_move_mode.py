from handmouse.move_mode import MoveModeConfig, MoveModeController, MoveModeState


def test_requires_stable_pose_before_becoming_active() -> None:
    controller = MoveModeController(MoveModeConfig(arm_dwell_ms=150, pose_loss_grace_ms=80))

    first = controller.update(clutch_down=True, move_pose=True, now_ms=0)
    second = controller.update(clutch_down=True, move_pose=True, now_ms=100)
    third = controller.update(clutch_down=True, move_pose=True, now_ms=160)

    assert first.state is MoveModeState.ARMED
    assert second.state is MoveModeState.ARMED
    assert third.state is MoveModeState.ACTIVE


def test_clutch_release_exits_immediately() -> None:
    controller = MoveModeController(MoveModeConfig(arm_dwell_ms=100, pose_loss_grace_ms=80))

    controller.update(clutch_down=True, move_pose=True, now_ms=0)
    controller.update(clutch_down=True, move_pose=True, now_ms=120)
    released = controller.update(clutch_down=False, move_pose=True, now_ms=121)

    assert released.state is MoveModeState.NEUTRAL
    assert released.movement_enabled is False


def test_brief_pose_loss_during_active_does_not_enable_other_modes() -> None:
    controller = MoveModeController(MoveModeConfig(arm_dwell_ms=100, pose_loss_grace_ms=80))

    controller.update(clutch_down=True, move_pose=True, now_ms=0)
    controller.update(clutch_down=True, move_pose=True, now_ms=120)
    lost = controller.update(clutch_down=True, move_pose=False, now_ms=150)

    assert lost.state is MoveModeState.ARMED
    assert lost.movement_enabled is False
