"""Conservative three-way merge for JSON state on a shared Git branch.

This is a standalone prototype, not a production Rosario integration.
Supply base (the version both writers read), local, and current remote.
Do not run this against production without adapting its field semantics.
"""
from copy import deepcopy
import json

_MISSING = object()

class StateConflict(ValueError):
    """Never quietly guess which incompatible state transition should win."""

def _key(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))

def _equal(a, b):
    if a is _MISSING or b is _MISSING:
        return a is b
    return a == b

def _append_only(base, local, remote, path):
    if not all(isinstance(x, list) for x in (base, local, remote)):
        raise StateConflict(f"{path}: incompatible collection types")
    # A list from a different writer must retain its entire original prefix.
    if local[:len(base)] != base or remote[:len(base)] != base:
        raise StateConflict(f"{path}: deletion, reordering or edits to prior list")
    combined = deepcopy(base)
    seen = {_key(x) for x in combined}
    for record in remote[len(base):] + local[len(base):]:
        marker = _key(record)
        if marker not in seen:
            combined.append(deepcopy(record))
            seen.add(marker)
    return combined

def _merge(base, local, remote, path):
    if _equal(local, remote):
        return _MISSING if local is _MISSING else deepcopy(local)
    if _equal(local, base):
        return _MISSING if remote is _MISSING else deepcopy(remote)
    if _equal(remote, base):
        return _MISSING if local is _MISSING else deepcopy(local)

    if isinstance(base, dict) and isinstance(local, dict) and isinstance(remote, dict):
        merged = {}
        for key in sorted(set(base) | set(local) | set(remote)):
            value = _merge(base.get(key, _MISSING),
                           local.get(key, _MISSING),
                           remote.get(key, _MISSING),
                           f"{path}.{key}")
            if value is not _MISSING:
                merged[key] = value
        return merged

    # Allow independent changes to previously absent dictionaries.
    if base is _MISSING and isinstance(local, dict) and isinstance(remote, dict):
        return _merge({}, local, remote, path)

    if isinstance(base, list) and isinstance(local, list) and isinstance(remote, list):
        return _append_only(base, local, remote, path)
    if base is _MISSING and isinstance(local, list) and isinstance(remote, list):
        return _append_only([], local, remote, path)

    # No arbitrary max() for retry counters, timestamps, wt or full_ok:
    # those fields require actual production-specific state transitions.
    raise StateConflict(f"{path}: conflicting changes (manual review required)")

def merge_json_state(base, local, remote):
    """Return merged copy, or raise StateConflict; never mutate the inputs."""
    if not all(isinstance(x, dict) for x in (base, local, remote)):
        raise TypeError("Expected three JSON objects")
    return _merge(base, local, remote, "state")
