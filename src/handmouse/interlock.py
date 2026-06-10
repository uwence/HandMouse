from enum import Enum

class InterlockType(Enum):
    NONE = 0
    CLICK = 1
    GRAB = 2

class InteractionInterlock:
    def __init__(self) -> None:
        self._state = InterlockType.NONE

    def try_acquire(self, interlock_type: InterlockType) -> bool:
        if self._state == InterlockType.NONE or self._state == interlock_type:
            self._state = interlock_type
            return True
        return False

    def release(self, interlock_type: InterlockType) -> None:
        if self._state == interlock_type:
            self._state = InterlockType.NONE

    @property
    def is_active(self) -> bool:
        return self._state != InterlockType.NONE
