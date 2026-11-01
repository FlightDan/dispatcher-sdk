import tempfile
import unittest
from pathlib import Path

from dispatcher_sdk.orchestrator.projection_json import ProjectionJSONError, write_json_stream
from dispatcher_sdk.orchestrator.projection_storage import ProjectionStorage, ProjectionStorageError


class ProjectionJSONTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = ProjectionStorage(Path(self.tmp.name) / 'streams.db')

    def write(self, raw, chunks=None, **options):
        return write_json_stream(self.store, 's', chunks or [raw], total_bytes=len(raw),
                                 binding={'source': 'host'}, **options)

    def test_page_boundaries_preserve_direct_bytes_and_replay(self):
        raw = b'{"value":"' + b'a' * (256 * 1024 - 11) + '😊'.encode() + b'"}'
        chunks = [raw[:262144], raw[262144:262146], raw[262146:]]
        self.assertTrue(self.write(raw, chunks)['complete'])
        self.assertTrue(self.write(raw, chunks)['complete'])
        page = self.store.read('s', limit=4)
        self.assertEqual(b''.join(p['data'] for p in page['pages']), raw)

    def test_rejects_malformed_and_ambiguous_without_creating_stream(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":', b'[NaN]', b'[1e9999]',
                    b'"\\ud800"', b'"\xff"', b'[] true'):
            with self.subTest(raw=raw):
                with self.assertRaises(ProjectionJSONError):
                    self.write(raw, [raw[:1], raw[1:]] if len(raw) > 1 else [raw])
                with self.assertRaises(ProjectionStorageError):
                    self.store.inspect('s')

    def test_depth_limits_and_split_escapes(self):
        raw = b'{"\\u0061":1,"a":2}'
        with self.assertRaises(ProjectionJSONError):
            self.write(raw, [bytes([v]) for v in raw])
        with self.assertRaises(ProjectionJSONError):
            self.write(b'[[[]]]', max_depth=2)

    def test_wrong_length_and_limit(self):
        with self.assertRaises(ProjectionJSONError):
            write_json_stream(self.store, 's', [b'{}'], total_bytes=3, binding={'x': 1})
        with self.assertRaises(ProjectionJSONError):
            self.write(b'{}', max_bytes=1)

    def test_large_incremental_input(self):
        chunk = b'x' * (256 * 1024)
        chunks = [b'"'] + [chunk] * 24 + [b'"']
        result = write_json_stream(self.store, 'large', iter(chunks),
            total_bytes=24 * len(chunk) + 2, binding={'source': 'host'})
        self.assertTrue(result['complete'])

    def test_surrogates_and_literals_across_single_byte_chunks(self):
        raw = b'{"a":"\\ud83d\\ude0a","b":[false,true,null,-3.2e-1]}'
        self.assertTrue(self.write(raw, [bytes([c]) for c in raw])['complete'])

    def test_key_count_bound(self):
        raw = ('{' + ','.join('"k%d":0' % i for i in range(4097)) + '}').encode()
        with self.assertRaises(ProjectionJSONError):
            self.write(raw)

    def test_resume_partial_only_with_same_pages(self):
        raw = b'"' + b'x' * (256 * 1024) + b'"'
        self.store.create('s', total_bytes=len(raw), binding={'source': 'host'})
        self.store.append('s', sequence=0, data=raw[:256 * 1024], complete=False)
        self.assertTrue(self.write(raw, [raw[:256 * 1024], raw[256 * 1024:]])['complete'])
        with self.assertRaises(ProjectionStorageError):
            self.write(raw.replace(b'x', b'y'), [raw.replace(b'x', b'y')[:256 * 1024], raw.replace(b'x', b'y')[256 * 1024:]])


if __name__ == '__main__':
    unittest.main()
