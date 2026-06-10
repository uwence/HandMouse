from __future__ import annotations

from typing import Any

from handmouse.hand_tracker import HandTrackingResult
from handmouse.types import FramePoint

def unify_hand_result(raw_result: HandTrackingResult, input_is_mirrored: bool) -> HandTrackingResult:
    """Unify the hand tracking result into an absolute physical coordinate space.
    
    In the Unified Physical Space, X=0 is always the physical left side of the user,
    and X=1 is the physical right side. This means moving the physical hand to the
    right always increases X.
    
    If the input image is non-mirrored (standard camera), the physical right hand
    appears on the left side of the image, so moving right means moving towards X=0.
    In this case, we map X -> 1.0 - X to unify it.
    
    If the input image is mirrored (hardware mirrored), the physical right hand
    appears on the right side of the image, so X maps directly.
    
    Args:
        raw_result: The raw result from MediaPipe based on the raw camera frame.
        input_is_mirrored: True if the raw camera frame is horizontally mirrored.
        
    Returns:
        A new HandTrackingResult in Unified Physical Space.
    """
    unified_landmarks: list[FramePoint] = []
    
    for lm in raw_result.landmarks:
        # Map X-coordinate
        new_x = lm.x if input_is_mirrored else (1.0 - lm.x)
        unified_landmarks.append(FramePoint(x=new_x, y=lm.y))

    # Re-extract tips from the unified landmarks
    thumb_tip = unified_landmarks[4] if len(unified_landmarks) > 4 else None
    index_tip = unified_landmarks[8] if len(unified_landmarks) > 8 else None

    # MediaPipe assumes the image is looking at the user (unmirrored selfie).
    # If the image is unmirrored, it correctly predicts handedness (Right = Right).
    # If the image is mirrored, it incorrectly reverses handedness (Right -> Left).
    # Therefore, if input_is_mirrored is True, we must reverse the label to get physical handedness.
    unified_label = raw_result.handedness_label
    if unified_label is not None and input_is_mirrored:
        if unified_label.lower() == "left":
            unified_label = "Right"
        elif unified_label.lower() == "right":
            unified_label = "Left"

    return HandTrackingResult(
        landmarks=unified_landmarks,
        thumb_tip=thumb_tip,
        index_tip=index_tip,
        raw_landmarks=raw_result.raw_landmarks,  # Keep raw format if needed internally
        handedness_label=unified_label,
        handedness_confidence=raw_result.handedness_confidence,
    )
