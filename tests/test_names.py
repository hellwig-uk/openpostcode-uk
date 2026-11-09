import unittest

import pandas as pd

from openpostcode.names import (
    is_blank,
    normalise_postcode,
    pick_bilingual,
    place_label,
    road_label,
    text_or_none,
)


class NamesTests(unittest.TestCase):
    def test_is_blank(self):
        self.assertTrue(is_blank(None))
        self.assertTrue(is_blank(""))
        self.assertTrue(is_blank("  "))
        self.assertTrue(is_blank(float("nan")))
        self.assertTrue(is_blank(pd.NA))
        self.assertFalse(is_blank("Mall"))
        self.assertFalse(is_blank([1, 2]))

    def test_labels(self):
        self.assertEqual(pick_bilingual("Heol", "Mall"), "Mall")
        self.assertEqual(pick_bilingual("Heol", None), "Heol")
        self.assertEqual(road_label("Heol", "Mall", "A1"), ("Mall", 0))
        self.assertEqual(road_label("Heol", None, "A1"), ("Heol", 0))
        self.assertEqual(road_label(None, None, "A302"), ("A302", 0))
        self.assertEqual(road_label(None, None, None), ("unnamed", 1))
        self.assertEqual(place_label("Palas", "Palace"), "Palace")
        self.assertEqual(place_label("Hill", None), "Hill")
        self.assertEqual(place_label(None, None), "unnamed")
        self.assertIsNone(text_or_none(None))

    def test_postcode(self):
        self.assertEqual(normalise_postcode("sw1a 1aa"), "SW1A1AA")
        self.assertEqual(normalise_postcode("SW1A1AA"), "SW1A1AA")
