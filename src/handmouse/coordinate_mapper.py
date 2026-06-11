from __future__ import annotations

from typing import Any

from handmouse.hand_tracker import HandTrackingResult
from handmouse.types import FramePoint

# Mutable debug metrics written by app._is_palm_facing_camera and read by
# debug_view. Defined at module level so writers don't need to do
# `hasattr` checks and so the value is always a str (never the absence of
# an attribute).
DEBUG_CROSS: str = ""

def unify_hand_result(raw_result: HandTrackingResult, input_is_mirrored: bool) -> HandTrackingResult:
    """Unify the hand tracking result into an absolute physical coordinate space.
    
    In the Unified Physical Space, X=0 is always the physical left side of the user,
    and X=1 is the physical right side. This means moving the physical hand to the
    right always increases X.
    
    Because camera.py now forces all frames to be mirrored before inference,
    the raw landmarks are already in a mirrored coordinate space. In a mirrored
    space, X naturally increases to the right. Therefore, we can use the raw
    coordinates and raw labels directly without any mapping.
    
    Args:
        raw_result: The raw result from MediaPipe based on the mirrored camera frame.
        input_is_mirrored: True if the hardware camera is horizontally mirrored.
        
    Returns:
        A new HandTrackingResult in Unified Physical Space.
    """
    unified_landmarks: list[FramePoint] = []
    
    for lm in raw_result.landmarks:
        # Since the input to MediaPipe is always mirrored, X naturally increases to the right.
        unified_landmarks.append(FramePoint(x=lm.x, y=lm.y))

    # Re-extract tips from the unified landmarks
    thumb_tip = unified_landmarks[4] if len(unified_landmarks) > 4 else None
    index_tip = unified_landmarks[8] if len(unified_landmarks) > 8 else None

    # MediaPipe receives a mirrored frame, so it correctly predicts physical handedness.
    unified_label = raw_result.handedness_label

    return HandTrackingResult(
        landmarks=unified_landmarks,
        thumb_tip=thumb_tip,
        index_tip=index_tip,
        raw_landmarks=raw_result.raw_landmarks,
        world_landmarks=getattr(raw_result, "world_landmarks", None),
        handedness_label=unified_label,
        handedness_confidence=raw_result.handedness_confidence,
    )
