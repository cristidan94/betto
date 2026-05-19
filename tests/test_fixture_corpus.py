from __future__ import annotations

import unittest
from pathlib import Path

from sports.cs.fixtures import load_fixture_corpus


class FixtureCorpusTests(unittest.TestCase):
    def test_load_fixture_corpus_from_directory(self) -> None:
        matches = load_fixture_corpus(Path("tests/fixtures/corpus"))

        self.assertEqual(len(matches), 6)
        self.assertEqual(matches[0].hltv_id, "2370001")

    def test_load_fixture_corpus_from_file(self) -> None:
        matches = load_fixture_corpus(Path("tests/fixtures/cs_match_001.json"))

        self.assertEqual(len(matches), 1)


if __name__ == "__main__":
    unittest.main()

