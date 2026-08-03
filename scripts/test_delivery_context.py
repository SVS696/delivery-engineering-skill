from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("delivery_context.py")
SPEC = importlib.util.spec_from_file_location("delivery_context", MODULE_PATH)
assert SPEC and SPEC.loader
context = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(context)


class DeliveryContextTests(unittest.TestCase):
    def test_map_validates(self) -> None:
        result = context.validate()
        self.assertEqual(result["routes"], 8)
        self.assertEqual(result["sources"], 10)

    def test_backend_route(self) -> None:
        selected = context.choose("Нужно изменить backend HTTP API endpoint")
        self.assertEqual(selected[0]["id"], "backend-http")

    def test_default_route(self) -> None:
        selected = context.choose("небольшое изменение")
        self.assertEqual(selected[0]["id"], "core-change")

    def test_extract_is_bounded(self) -> None:
        body = context.extract("codebase-conformance")
        self.assertIn("E03. Иерархия локального канона", body)
        self.assertNotIn("E08. Evidence проверок", body)


if __name__ == "__main__":
    unittest.main()
