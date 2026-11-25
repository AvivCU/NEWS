"""Offline event proximity helper; callers decide identity and publication."""
from __future__ import annotations


def nearby_event(text, entity_pattern, event_predicate, before_words=5, after_words=8):
    for match in entity_pattern.finditer(text):
        before = text[:match.start()].split()[-before_words:] if before_words else []
        after = text[match.end():].split()[:after_words]
        if event_predicate(" ".join(before + after)):
            return True
    return False
