import threading

class CalibrationState:
    def __init__(self):
        self.lock = threading.Lock()
        self.active = False
        self.last_pinch_ratio = 0.0
        self.last_palm_span = 0.0
        self.captured_ratios = []

    def update(self, pinch_ratio: float, palm_span: float):
        with self.lock:
            if self.active:
                self.last_pinch_ratio = pinch_ratio
                self.last_palm_span = palm_span
                self.captured_ratios.append(pinch_ratio)

    def start(self):
        with self.lock:
            self.active = True
            self.captured_ratios.clear()
            self.last_pinch_ratio = 0.0
            self.last_palm_span = 0.0

    def stop(self):
        with self.lock:
            self.active = False

    def get_summary(self):
        with self.lock:
            if not self.captured_ratios:
                return 0.0, 0.0, 0.0
            avg_ratio = sum(self.captured_ratios) / len(self.captured_ratios)
            min_ratio = min(self.captured_ratios)
            max_ratio = max(self.captured_ratios)
            return avg_ratio, min_ratio, max_ratio

STATE = CalibrationState()
