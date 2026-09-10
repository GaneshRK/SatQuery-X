from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace


def _hash(prev, payload):
    body = {"prev_hash": prev, "payload": payload}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def test_hash_chain_detects_tampering():
    payloads = [{"event": "a"}, {"event": "b"}, {"event": "c"}]
    previous = ""
    hashes = []
    for payload in payloads:
        current = _hash(previous or None, payload)
        hashes.append(current)
        previous = current
    assert hashes[1] == _hash(hashes[0], payloads[1])
    payloads[1]["event"] = "tampered"
    assert hashes[1] != _hash(hashes[0], payloads[1])
