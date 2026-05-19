from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.ingestion import FetchResult
from core.raw_store import LocalRawStore


class LocalRawStoreTests(unittest.TestCase):
    def test_put_persists_body_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalRawStore(Path(tmp))
            result = FetchResult.from_text("source", "id/1", "https://example.test", "hello")

            obj = store.put(result)

            self.assertTrue(obj.body_path.exists())
            self.assertTrue(obj.metadata_path.exists())
            self.assertEqual(store.read_bytes(obj), b"hello")


if __name__ == "__main__":
    unittest.main()

