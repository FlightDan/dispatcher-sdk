"""Incremental strict JSON validation and direct-byte projection storage.

This helper does not normalize bytes, validate the application schema, or
provide source authentication or authority to install a projection.
"""
from __future__ import annotations

import codecs
import json
import math
import re
import tempfile

from .projection_storage import MAX_PAGE_BYTES, MAX_STREAM_BYTES, ProjectionStorage

MAX_JSON_BYTES = MAX_STREAM_BYTES
MAX_KEY_BYTES = 65536
MAX_OBJECT_KEYS = 4096
MAX_OBJECT_KEY_BYTES = 1024 * 1024
MAX_NUMBER_CHARS = 1024
_NUMBER = re.compile(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?\Z')


class ProjectionJSONError(ValueError):
    """Input is not a bounded, unambiguous UTF-8 JSON document."""


class _Validator:
    def __init__(self, max_depth):
        self.max_depth = max_depth
        self.stack = []
        self.root = 'value'
        self.mode = None
        self.token = ''
        self.key = False
        self.escape = None
        self.hex = ''
        self.high = False
        self.key_length = 0

    def _number_done(self):
        if not _NUMBER.fullmatch(self.token):
            raise ProjectionJSONError('invalid JSON number')
        if any(c in self.token for c in '.eE') and not math.isfinite(float(self.token)):
            raise ProjectionJSONError('non-finite JSON number')

    def _state(self):
        return self.stack[-1]['state'] if self.stack else self.root

    def _set(self, value):
        if self.stack:
            self.stack[-1]['state'] = value
        else:
            self.root = value

    def _value(self):
        state = self._state()
        if state not in ('value', 'value_or_end'):
            raise ProjectionJSONError('unexpected JSON value')
        self._set('done' if not self.stack else 'comma_or_end')

    def _push(self, kind):
        self._value()
        if len(self.stack) >= self.max_depth:
            raise ProjectionJSONError('JSON nesting exceeds limit')
        self.stack.append({'kind': kind, 'state': 'key_or_end' if kind == '{' else 'value_or_end',
                           'keys': set(), 'key_bytes': 0})

    def _string_char(self, char):
        if self.key:
            self.token += char
            self.key_length += len(char.encode('utf-8'))
            if self.key_length > MAX_KEY_BYTES:
                raise ProjectionJSONError('JSON object key exceeds limit')
        if self.escape == 'low_slash':
            if char != '\\':
                raise ProjectionJSONError('unpaired JSON surrogate')
            self.escape = 'low_u'
        elif self.escape == 'low_u':
            if char != 'u':
                raise ProjectionJSONError('unpaired JSON surrogate')
            self.escape = 'unicode'
            self.hex = ''
        elif self.escape == 'unicode':
            if char not in '0123456789abcdefABCDEF':
                raise ProjectionJSONError('invalid JSON unicode escape')
            self.hex += char
            if len(self.hex) == 4:
                number = int(self.hex, 16)
                if self.high:
                    if not 0xDC00 <= number <= 0xDFFF:
                        raise ProjectionJSONError('unpaired JSON surrogate')
                    self.high = False
                    self.escape = None
                elif 0xD800 <= number <= 0xDBFF:
                    self.high = True
                    self.escape = 'low_slash'
                elif 0xDC00 <= number <= 0xDFFF:
                    raise ProjectionJSONError('unpaired JSON surrogate')
                else:
                    self.escape = None
        elif self.escape == 'slash':
            if char == 'u':
                self.escape, self.hex = 'unicode', ''
            elif char in '"\\/bfnrt':
                self.escape = None
            else:
                raise ProjectionJSONError('invalid JSON escape')
        elif char == '\\':
            self.escape = 'slash'
        elif char == '"':
            self.mode = None
            if self.key:
                key = json.loads(self.token)
                frame = self.stack[-1]
                if key in frame['keys']:
                    raise ProjectionJSONError('duplicate JSON object key')
                frame['key_bytes'] += len(key.encode('utf-8'))
                if len(frame['keys']) >= MAX_OBJECT_KEYS or frame['key_bytes'] > MAX_OBJECT_KEY_BYTES:
                    raise ProjectionJSONError('JSON object keys exceed limit')
                frame['keys'].add(key)
                frame['state'] = 'colon'
                self.token = ''
        elif ord(char) < 32:
            raise ProjectionJSONError('invalid JSON string control character')

    def feed(self, text):
        index = 0
        while index < len(text):
            char = text[index]
            if self.mode == 'string':
                self._string_char(char)
            elif self.mode == 'number':
                if char in '0123456789.eE+-':
                    self.token += char
                    if len(self.token) > MAX_NUMBER_CHARS:
                        raise ProjectionJSONError('JSON number exceeds limit')
                else:
                    self._number_done()
                    self.mode = None
                    continue
            elif self.mode == 'literal':
                self.token += char
                if not self.literal.startswith(self.token):
                    raise ProjectionJSONError('invalid JSON literal')
                if self.token == self.literal:
                    self.mode = None
            elif char in ' \t\r\n':
                pass
            elif char == '"':
                self.key = bool(self.stack and self.stack[-1]['kind'] == '{' and self._state() in ('key', 'key_or_end'))
                if not self.key:
                    self._value()
                self.mode, self.token, self.escape, self.high = 'string', '"' if self.key else '', None, False
                self.key_length = 1
            elif char in '[{':
                self._push(char)
            elif char in ']}':
                if not self.stack or (self.stack[-1]['kind'], char) not in (('[', ']'), ('{', '}')):
                    raise ProjectionJSONError('invalid JSON nesting')
                state = self._state()
                if state not in ('comma_or_end', 'value_or_end' if char == ']' else 'key_or_end'):
                    raise ProjectionJSONError('invalid JSON container ending')
                self.stack.pop()
            elif char == ':':
                if self._state() != 'colon':
                    raise ProjectionJSONError('unexpected JSON colon')
                self._set('value')
            elif char == ',':
                if not self.stack or self._state() != 'comma_or_end':
                    raise ProjectionJSONError('unexpected JSON comma')
                self._set('key' if self.stack[-1]['kind'] == '{' else 'value')
            elif char in '-0123456789':
                self._value()
                self.mode, self.token = 'number', char
            elif char in 'tfn':
                self._value()
                self.mode, self.token, self.literal = 'literal', char, {'t': 'true', 'f': 'false', 'n': 'null'}[char]
            else:
                raise ProjectionJSONError('invalid JSON character')
            index += 1

    def finish(self):
        if self.mode == 'number':
            self._number_done()
            self.mode = None
        if self.mode or self.stack or self.root != 'done':
            raise ProjectionJSONError('incomplete JSON document')


def write_json_stream(storage: ProjectionStorage, stream_id: str, chunks, *, total_bytes: int,
                      binding: dict, max_bytes: int = MAX_JSON_BYTES, max_depth: int = 64) -> dict:
    """Validate bounded UTF-8 chunks, then store original bytes without normalization.

    Objects are limited to 4096 keys and 1 MiB of decoded key text, each key
    to 64 KiB of encoded JSON, numbers to 1024 characters, and depth to 128.
    Invalid input creates no stream; interrupted storage can replay exact bytes.
    Input is spooled to a temporary file; no full document is loaded in memory.
    """
    if not isinstance(storage, ProjectionStorage):
        raise TypeError('storage must be ProjectionStorage')
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_JSON_BYTES:
        raise ValueError('invalid JSON byte limit')
    if type(max_depth) is not int or not 1 <= max_depth <= 128:
        raise ValueError('invalid JSON depth limit')
    if type(total_bytes) is not int or not 1 <= total_bytes <= max_bytes:
        raise ProjectionJSONError('JSON size exceeds limit')
    validator = _Validator(max_depth)
    decoder = codecs.getincrementaldecoder('utf-8')('strict')
    with tempfile.TemporaryFile() as source:
        count = 0
        try:
            for chunk in chunks:
                if type(chunk) is not bytes or not chunk or len(chunk) > MAX_PAGE_BYTES:
                    raise ProjectionJSONError('invalid JSON input chunk')
                count += len(chunk)
                if count > total_bytes:
                    raise ProjectionJSONError('JSON input exceeds declared size')
                validator.feed(decoder.decode(chunk))
                source.write(chunk)
            if count != total_bytes:
                raise ProjectionJSONError('JSON input is incomplete')
            validator.feed(decoder.decode(b'', final=True))
            validator.finish()
        except (UnicodeError, RecursionError) as exc:
            raise ProjectionJSONError('invalid UTF-8 JSON document') from exc
        storage.create(stream_id, total_bytes=total_bytes, binding=binding)
        source.seek(0)
        sequence, remaining = 0, total_bytes
        while remaining:
            page = source.read(min(MAX_PAGE_BYTES, remaining))
            if not page:
                raise ProjectionJSONError('validated input became unavailable')
            remaining -= len(page)
            result = storage.append(stream_id, sequence=sequence, data=page, complete=remaining == 0)
            sequence += 1
        return result
