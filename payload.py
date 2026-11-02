#!/usr/bin/env python3
"""Standard-library-only encoder/inspector for the statically recovered schema.

This module constructs local bytes; it makes no network requests.
"""
import argparse
import json
import re
import secrets
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMA = json.loads((HERE / 'schema.json').read_text())
MESSAGES = SCHEMA['messages']
ENUMS = {name: {item['name']: item['value'] for item in items}
         for name, items in SCHEMA['enums'].items()}


def varint(value):
    if type(value) is not int or not 0 <= value < 1 << 64:
        raise ValueError('varint requires uint64')
    out = bytearray()
    while value >= 128:
        out.append((value & 127) | 128)
        value >>= 7
    out.append(value)
    return bytes(out)


def _integer(value, bits, field):
    if type(value) is not int or not -(1 << (bits - 1)) <= value < 1 << (bits - 1):
        raise ValueError(f'{field}: expected signed int{bits}')
    return value


def _scalar(field, value):
    kind, label = field['type'], field['name']
    if kind in MESSAGES:
        if not isinstance(value, dict):
            raise TypeError(f'{label}: expected message dictionary')
        return encode_message(kind, value), False
    if kind == 'string':
        if not isinstance(value, str):
            raise TypeError(f'{label}: expected string; preserve long IDs as strings')
        return value.encode('utf-8'), value == ''
    if kind == 'bool':
        if type(value) is not bool:
            raise TypeError(f'{label}: expected bool')
        return varint(int(value)), value is False
    if kind in ENUMS:
        if isinstance(value, str):
            try:
                value = ENUMS[kind][value]
            except KeyError:
                raise ValueError(f'{label}: unknown {kind} name {value!r}') from None
        value = _integer(value, 32, label)
    else:
        value = _integer(value, 64 if kind == 'int64' else 32, label)
    return varint(value & ((1 << 64) - 1)), value == 0


def encode_message(message_type, values):
    """Encode proto or Swift property names; omit default-valued scalar fields.

    Message dictionaries retain presence, including an explicitly empty {}.
    Repeated strings retain empty elements. Unknown keys and duplicate aliases fail.
    """
    if message_type not in MESSAGES or not isinstance(values, dict):
        raise ValueError('expected known message type and dictionary')
    aliases = {}
    for f in MESSAGES[message_type]['fields']:
        aliases[f['name']] = aliases[f['swift_name']] = f
    selected = {}
    for name, value in values.items():
        if name not in aliases:
            raise ValueError(f'{message_type}: unknown field {name!r}')
        f = aliases[name]
        if f['number'] in selected:
            raise ValueError(f'{message_type}: duplicate aliases for {f["name"]}')
        selected[f['number']] = (f, value)
    out = bytearray()
    for number in sorted(selected):
        f, value = selected[number]
        if f['repeated']:
            if not isinstance(value, (list, tuple)):
                raise TypeError(f'{f["name"]}: expected list of strings')
            items = value
        else:
            items = [value]
        for item in items:
            raw, default = _scalar(f, item)
            if default and not f['repeated']:
                continue
            out += varint((number << 3) | f['wire_type'])
            if f['wire_type'] == 2:
                out += varint(len(raw))
            out += raw
    return bytes(out)


def read_varint(data, offset=0):
    value = 0
    for index in range(10):
        if offset >= len(data):
            raise ValueError('truncated varint')
        byte = data[offset]
        offset += 1
        if index == 9 and byte > 1:
            raise ValueError('varint exceeds uint64')
        value |= (byte & 127) << (index * 7)
        if byte < 128:
            return value, offset
    raise ValueError('invalid varint')


def decode_message(message_type, data):
    """Inspect serialized fields; supports all wire types used by this schema.

    Unknown fields are shown under $unknown; this is an inspector, not a lossless
    protobuf object model. Duplicate singular messages are not merge-normalized.
    """
    fields = {f['number']: f for f in MESSAGES[message_type]['fields']}
    result, offset = {}, 0
    while offset < len(data):
        start = offset
        tag, offset = read_varint(data, offset)
        number, wire = tag >> 3, tag & 7
        if not 1 <= number < (1 << 29):
            raise ValueError('invalid protobuf field number')
        if wire == 0:
            value, offset = read_varint(data, offset)
        elif wire in (1, 2, 5):
            if wire == 2:
                length, offset = read_varint(data, offset)
            else:
                length = 8 if wire == 1 else 4
            if length > len(data) - offset:
                raise ValueError('truncated protobuf field')
            value, offset = data[offset:offset + length], offset + length
        else:
            raise ValueError('unsupported wire type, including legacy groups')
        f = fields.get(number)
        if f is None:
            result.setdefault('$unknown', []).append(dict(number=number, wire_type=wire,
                                                         hex=data[start:offset].hex()))
            continue
        if wire != f['wire_type']:
            raise ValueError(f'{f["name"]}: unexpected wire type {wire}')
        kind = f['type']
        if kind in MESSAGES:
            value = decode_message(kind, value)
        elif kind == 'string':
            value = value.decode('utf-8')
        elif kind == 'bool':
            value = bool(value)
        elif kind in ENUMS or kind in ('int32', 'int64'):
            bits = 64 if kind == 'int64' else 32
            value &= (1 << bits) - 1
            if value >= 1 << (bits - 1):
                value -= 1 << bits
        if f['repeated']:
            result.setdefault(f['name'], []).append(value)
        else:
            result[f['name']] = value
    return result


def frame_message(raw):
    """SwiftProtobuf stream format at 0x1015dd3f4: varint(length) + Log."""
    if not isinstance(raw, bytes):
        raise TypeError('raw message must be bytes')
    return varint(len(raw)) + raw


def decode_delimited(data):
    """Inspect one or more consecutive length-prefixed Log messages."""
    messages, offset = [], 0
    while offset < len(data):
        length, offset = read_varint(data, offset)
        if length > len(data) - offset:
            raise ValueError('truncated delimited message')
        messages.append(decode_message('Log', data[offset:offset + length]))
        offset += length
    return messages


def build_feed_detail(feed_id=None, public_meta=None, page_meta=None, basic_meta=None,
                      delimited=True):
    """Build one E_PAGE_VIEW / P_FEED_DETAIL Log, without inventing device values.

    feed_id, if supplied, is placed in PageViewMeta.feedIdList. This parameter is
    a schema-level convenience; the server's attribution rule is not established.
    No timestamp, session identifier or device identifier is auto-generated.
    Default output includes the length prefix used by the actual upload path.
    Set delimited=False only when a bare Log message is required.
    """
    public = dict(public_meta or {})
    public['event'] = 'E_PAGE_VIEW'
    page = dict(page_meta or {})
    page['pageEnum'] = 'P_FEED_DETAIL'
    if feed_id is not None:
        if not isinstance(feed_id, str):
            raise TypeError('feed_id must be a string')
        if 'feedIdList' in page or 'feedIDList' in page:
            raise ValueError('provide feed_id or a feedIdList, not both')
        page['feedIdList'] = [feed_id]
    log = dict(publicMeta=public, pageViewMeta=page)
    if basic_meta is not None:
        log['basicMeta'] = dict(basic_meta)
    raw = encode_message('Log', log)
    return frame_message(raw) if delimited else raw


def multipart_body(payload, boundary=None, extra_parts=()):
    """Return (Content-Type, body). File part first, then optional text/raw parts.

    extra_parts is a sequence of (name, str|bytes) pairs; use debugData only when
    intentionally matching that observed conditional branch. No extra auth part
    is invented. The boundary can be fixed for byte-for-byte local fixtures.
    """
    if not isinstance(payload, bytes):
        raise TypeError('payload must be bytes')
    if boundary is None:
        boundary = 'alamofire.boundary.' + secrets.token_hex(8)
    if not isinstance(boundary, str) or not re.fullmatch(r'[A-Za-z0-9._-]{1,70}', boundary):
        raise ValueError('boundary must contain 1–70 ASCII letters/digits/._-')
    parts = [(b'Content-Disposition: form-data; name="message"; filename="message"\r\n'
              b'Content-Type: application/octet-stream\r\n\r\n', payload)]
    for name, value in extra_parts:
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9._-]+', name):
            raise ValueError('invalid extra part name')
        if isinstance(value, str):
            value = value.encode('utf-8')
        if not isinstance(value, bytes):
            raise TypeError('extra part value must be str or bytes')
        header = f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode('ascii')
        parts.append((header, value))
    marker = boundary.encode('ascii')
    if any(b'--' + marker in value for _, value in parts):
        raise ValueError('boundary collides with part content; choose another boundary')
    body = b''.join(b'--' + marker + b'\r\n' + header + value + b'\r\n'
                    for header, value in parts) + b'--' + marker + b'--\r\n'
    return 'multipart/form-data; boundary=' + boundary, body


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', type=Path, help='Log dictionary; defaults to minimal P_FEED_DETAIL')
    parser.add_argument('--out', type=Path, default=HERE / 'examples')
    args = parser.parse_args()
    raw = encode_message('Log', json.loads(args.json.read_text())) if args.json else build_feed_detail(delimited=False)
    framed = frame_message(raw)
    content_type, body = multipart_body(framed, boundary='alamofire.boundary.0000000000000000')
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'message.pb').write_bytes(raw)
    (args.out / 'message.delimited.pb').write_bytes(framed)
    (args.out / 'multipart.bin').write_bytes(body)
    (args.out / 'decoded.json').write_text(json.dumps(decode_message('Log', raw), indent=2, ensure_ascii=False) + '\n')
    print(json.dumps(dict(raw_message_bytes=len(raw), raw_message_hex=raw.hex(),
                          upload_payload_bytes=len(framed), upload_payload_hex=framed.hex(),
                          content_type=content_type, multipart_bytes=len(body)), indent=2))


if __name__ == '__main__':
    main()
