#!/usr/bin/env python3
"""Reproduce sohuhy 6.24.1 feeds/show sig, using only Python's standard library.

Input params are decoded form values, before application/x-www-form-urlencoded
escaping. The target endpoint uses string/integer scalars. This module does not
claim to reproduce Swift/Alamofire's rendering of arrays or nested dictionaries.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping

DEFAULT_KEY_MATERIAL = b"C01N6rm43032SV00"
SIGNED_HEADERS = ("S-CID", "S-PID", "S-PPID", "S-VS", "s-nonce")
_SIGNED_HEADER_NAMES = frozenset(h.lower() for h in SIGNED_HEADERS)


def _scalar(value):
    if isinstance(value, str):
        return value
    if type(value) is int:
        return str(value)
    raise TypeError("feeds/show parameters must be decoded strings or integers")


def canonical_message(params: dict, headers: dict,
                      key_material: str | bytes = DEFAULT_KEY_MATERIAL) -> bytes:
    """Return the exact UTF-8 bytes passed into CryptoSwift MD5.

    Header lookup is case-insensitive; signed header names are canonicalized to
    the spelling used by SHRequestSigInfo. All five headers are required by this
    captured-request profile. An existing sig is ignored. The app's optional
    internal appKey parameter overrides the suffix and is removed from the pairs.
    """
    if not isinstance(params, Mapping) or not isinstance(headers, Mapping):
        raise TypeError("params and headers must be mappings")
    if any(not isinstance(k, str) or not k.isascii() for k in params):
        raise TypeError("this endpoint profile requires ASCII parameter names")
    values = {k: _scalar(v) for k, v in params.items()
              if k not in ("sig", "appKey")}
    normalized = {}
    for name, value in headers.items():
        if not isinstance(name, str):
            raise TypeError("header names must be strings")
        lower = name.lower()
        if lower not in _SIGNED_HEADER_NAMES:
            continue
        text = _scalar(value)
        if lower in normalized and normalized[lower] != text:
            raise ValueError(f"conflicting duplicate header: {name}")
        normalized[lower] = text
    for name in SIGNED_HEADERS:
        if name.lower() not in normalized:
            raise ValueError(f"missing signed header: {name}")
        values[name] = normalized[name.lower()]
    if "appKey" in params:
        key_material = _scalar(params["appKey"])
    if isinstance(key_material, str):
        suffix = key_material.encode("utf-8")
    elif isinstance(key_material, bytes):
        suffix = key_material
    else:
        raise TypeError("key_material must be str or bytes")
    pairs = "".join(f"{k}={values[k]}" for k in sorted(values))
    return pairs.encode("utf-8") + suffix


def sign(params: dict, headers: dict,
         key_material: str | bytes = DEFAULT_KEY_MATERIAL) -> str:
    """Return the lowercase, zero-padded 32-character MD5 hexadecimal sig."""
    return hashlib.md5(canonical_message(params, headers, key_material)).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="JSON file with params and headers; '-' for stdin")
    parser.add_argument("--key-material", default=None, help="override the default suffix")
    parser.add_argument("--explain", action="store_true", help="print canonical message and sig")
    args = parser.parse_args()
    if args.input == "-":
        data = json.load(sys.stdin)
    else:
        with open(args.input, encoding="utf-8") as source:
            data = json.load(source)
    key = DEFAULT_KEY_MATERIAL if args.key_material is None else args.key_material
    result = sign(data["params"], data["headers"], key)
    if args.explain:
        message = canonical_message(data["params"], data["headers"], key)
        print(json.dumps({"sig": result, "message_utf8": message.decode("utf-8"),
                          "message_hex": message.hex(), "byte_length": len(message)},
                         ensure_ascii=False, indent=2))
    else:
        print(result)


if __name__ == "__main__":
    main()
