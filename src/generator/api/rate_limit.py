"""A run costs model tokens, so only one generate run goes at a time."""

import threading

RUN_LOCK = threading.Lock()
