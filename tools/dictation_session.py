"""Bound best-effort dictation hotkeys to the window that accepted START."""
import time

class DictationSession:
    def __init__(self, toggle, clock=time.monotonic, log=print):
        self.toggle, self.clock, self.log = toggle, clock, log
        self.target = None
        self.ready = 0.0
        self.stop_at = self.expires = None

    def start(self):
        self.stop_at = self.expires = None
        if self.target is not None:
            # Rapid re-press while the previous tail drains stays in that same take.
            return
        self.target = self.toggle() or None
        self.ready = self.clock() + 0.65
        self.log('Codex dictation START hotkey ' + ('sent' if self.target else 'skipped: focus Codex, release modifiers'))

    def finish(self):
        if self.target is not None and self.stop_at is None:
            self.stop_at = self.clock() + 0.25
            self.expires = self.clock() + 5.0

    def tick(self, drained):
        if self.stop_at is None:
            return
        now = self.clock()
        if now >= self.expires:
            self.log('Codex stop expired: stop dictation manually in the original window; no delayed hotkey will be sent.')
            self.target = None
            self.stop_at = self.expires = None
        elif now >= self.stop_at and drained:
            if self.toggle(expected_target=self.target):
                self.log('Codex dictation STOP hotkey sent')
                self.target = None
                self.stop_at = self.expires = None
            else:
                self.stop_at = now + 0.25
