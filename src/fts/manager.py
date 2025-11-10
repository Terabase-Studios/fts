import copy
import threading


class Manager:
    def __init__(self, no_dict=False):
        self._type = None
        self._progress = None
        self._max_progress = None
        self._state = None
        self._cancelled = False
        self._finished = False
        self._in_use = False
        self.no_dict = no_dict

        # One reentrant lock protects all shared state
        self._lock = threading.RLock()

    # -------------------------
    # Type field
    # -------------------------
    @property
    def type(self):
        with self._lock:
            return self._type

    @type.setter
    def type(self, value):
        with self._lock:
            self._type = value

    # -------------------------
    # Progress, max_progress, state
    # -------------------------
    def _get_safe(self, attr):
        with self._lock:
            return copy.deepcopy(getattr(self, attr))

    def _set_safe(self, attr, value):
        with self._lock:
            setattr(self, attr, copy.deepcopy(value))

    @property
    def progress(self): return self._get_safe("_progress")
    @progress.setter
    def progress(self, v): self._set_safe("_progress", v)

    @property
    def max_progress(self): return self._get_safe("_max_progress")
    @max_progress.setter
    def max_progress(self, v): self._set_safe("_max_progress", v)

    @property
    def state(self): return self._get_safe("_state")
    @state.setter
    def state(self, v): self._set_safe("_state", v)

    # -------------------------
    # Flags
    # -------------------------
    @property
    def finished(self):
        with self._lock:
            return self._finished

    @finished.setter
    def finished(self, value: bool):
        with self._lock:
            self._finished = bool(value)

    @property
    def in_use(self):
        with self._lock:
            return self._in_use

    @in_use.setter
    def in_use(self, value: bool):
        with self._lock:
            self._in_use = bool(value)

    @property
    def cancelled(self):
        with self._lock:
            return self._cancelled

    @cancelled.setter
    def cancelled(self, value: bool):
        with self._lock:
            self._cancelled = bool(value)

    # -------------------------
    # Utilities
    # -------------------------
    def update_dict(self, attr: str, key, value):
        """Safely update a key in a dict-type attribute (progress, state, etc.)."""
        with self._lock:
            current = getattr(self, attr)
            if isinstance(current, dict):
                current[key] = value
            else:
                raise TypeError(f"{attr} is not a dict (currently {type(current).__name__})")

    def reset(self):
        """Reset all fields safely."""
        with self._lock:
            self._type = None
            self._progress = None
            self._max_progress = None
            self._state = None
            self._cancelled = False
            self._finished = False
            self._in_use = False