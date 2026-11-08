import unittest
from unittest import mock

from opennames.extract import _layer_fields, _layer_names, find_layer


class LayerHelperTests(unittest.TestCase):
    def test_layer_names_string_and_row(self):
        with mock.patch(
            "opennames.extract.pyogrio.list_layers",
            return_value=["only"],
        ):
            self.assertEqual(_layer_names("x"), ["only"])
        with mock.patch(
            "opennames.extract.pyogrio.list_layers",
            return_value=[("namedplace", "Point")],
        ):
            self.assertEqual(_layer_names("x"), ["namedplace"])

    def test_layer_fields_dict(self):
        with mock.patch(
            "opennames.extract.pyogrio.read_info",
            return_value={"fields": {"Name1": "str", "local_type": "str"}},
        ):
            self.assertEqual(_layer_fields("x", "l"), {"name1", "local_type"})
        with mock.patch(
            "opennames.extract.pyogrio.read_info",
            return_value={"fields": ["Name1", "local_type"]},
        ):
            self.assertEqual(_layer_fields("x", "l"), {"name1", "local_type"})
        with mock.patch(
            "opennames.extract.pyogrio.read_info",
            return_value={"fields": None, "dtypes": {"Name1": "str"}},
        ):
            self.assertEqual(_layer_fields("x", "l"), {"name1"})
