import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HAS_REQUESTS = importlib.util.find_spec("requests") is not None
if HAS_REQUESTS:
    from scripts.fetch_euroc import RemoteZip


class Response:
    def __init__(self, status, content_range, chunks=()):
        self.status_code, self.headers = status, {"Content-Range": content_range}
        self.chunks, self.body_read = chunks, False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def raise_for_status(self):
        pass

    def iter_content(self, size):
        self.body_read = True
        yield from self.chunks


@unittest.skipUnless(HAS_REQUESTS, "install scripts/requirements-vision.txt")
class BoundedArchiveDownloadTests(unittest.TestCase):
    def test_ignored_range_is_rejected_before_reading_the_large_archive_body(self):
        first, invalid = Response(206, "bytes 0-0/4"), Response(200, "", [b"large archive"])
        with tempfile.TemporaryDirectory(prefix="tepegoz-range-") as folder, patch("scripts.fetch_euroc.requests.get", side_effect=[first, invalid]) as get:
            archive = RemoteZip("https://example.test/dataset.zip", folder)
            with self.assertRaisesRegex(ValueError, "wrong byte range"):
                archive.read(4)
            self.assertFalse(invalid.body_read)
            self.assertTrue(all(call.kwargs["stream"] for call in get.call_args_list))
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_oversized_body_is_rejected_without_populating_cache(self):
        first, oversized = Response(206, "bytes 0-0/4"), Response(206, "bytes 0-3/4", [b"1234", b"5"])
        with tempfile.TemporaryDirectory(prefix="tepegoz-range-") as folder, patch("scripts.fetch_euroc.requests.get", side_effect=[first, oversized]):
            archive = RemoteZip("https://example.test/dataset.zip", folder)
            with self.assertRaisesRegex(ValueError, "exceeds"):
                archive.read(4)
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_valid_range_supports_seek_and_reuses_verified_size_cache(self):
        first, block = Response(206, "bytes 0-0/4"), Response(206, "bytes 0-3/4", [b"12", b"34"])
        with tempfile.TemporaryDirectory(prefix="tepegoz-range-") as folder, patch("scripts.fetch_euroc.requests.get", side_effect=[first, block]) as get:
            archive = RemoteZip("https://example.test/dataset.zip", folder)
            self.assertEqual(archive.read(2), b"12"); archive.seek(-1, 2)
            self.assertEqual(archive.read(), b"4")
            self.assertEqual(get.call_count, 2)


if __name__ == "__main__":
    unittest.main()
