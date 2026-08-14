from __future__ import annotations

import importlib.util
import json
import tempfile
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
        self.assertEqual(result["sources"], 11)

    def test_backend_route(self) -> None:
        selected = context.choose("Нужно изменить backend HTTP API endpoint")
        self.assertEqual(selected[0]["id"], "backend-http")

    def test_default_route(self) -> None:
        selected = context.choose("небольшое изменение")
        self.assertEqual(selected[0]["id"], "core-change")

    def test_core_route_carries_native_simplicity(self) -> None:
        body = context.extract("core-change")
        self.assertIn("E09. Лестница реализации", body)
        self.assertIn("E10. Protected floor", body)
        self.assertIn("`revisit_trigger`", body)

    def test_extract_is_bounded(self) -> None:
        body = context.extract("codebase-conformance")
        self.assertIn("E03. Иерархия локального канона", body)
        self.assertNotIn("E08. Evidence проверок", body)

    def test_materialized_context_is_deterministic_and_lane_isolated(self) -> None:
        assignments = {
            "backend": ["backend-http", "risk-security"],
            "test": ["test-design"],
        }
        first_payload, first_contents = context.build_engineering_context(assignments)
        second_payload, second_contents = context.build_engineering_context(assignments)
        self.assertEqual(first_payload, second_payload)
        self.assertEqual(first_contents, second_contents)
        self.assertIn("B01. Ресурс", first_contents["backend"])
        self.assertNotIn("T01. Test basis", first_contents["backend"])
        self.assertIn("T01. Test basis", first_contents["test"])
        context.validate_engineering_context(
            first_payload,
            first_contents,
            expected_lanes={"backend", "test"},
            verify_sources=True,
        )

    def test_materialized_context_limits_routes_per_lane(self) -> None:
        with self.assertRaises(context.ContextError):
            context.build_engineering_context(
                {"backend": ["core-change", "backend-http", "risk-security"]}
            )

    def test_materialized_context_rejects_cross_lane_route(self) -> None:
        with self.assertRaises(context.ContextError):
            context.build_engineering_context({"backend": ["frontend-behavior"]})

    def test_tester_can_receive_test_and_surface_routes(self) -> None:
        payload, contents = context.build_engineering_context(
            {"test": ["test-design", "backend-http", "frontend-behavior"]}
        )
        context.validate_engineering_context(payload, contents)
        self.assertIn("T01. Test basis", contents["test"])
        self.assertIn("B01. Ресурс", contents["test"])
        self.assertIn("F01. Наблюдаемое", contents["test"])

    def test_tampered_basis_is_detected(self) -> None:
        payload, contents = context.build_engineering_context({"test": ["test-design"]})
        contents["test"] += "tampered\n"
        with self.assertRaises(context.ContextError):
            context.validate_engineering_context(payload, contents)

    def test_writer_refuses_overwrite(self) -> None:
        payload, contents = context.build_engineering_context({"test": ["test-design"]})
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "case"
            context.write_engineering_context(root, payload, contents)
            stored = json.loads(
                (root / context.ENGINEERING_CONTEXT_JSON).read_text(encoding="utf-8")
            )
            self.assertEqual(stored["fingerprint"], payload["fingerprint"])
            with self.assertRaises(context.ContextError):
                context.write_engineering_context(root, payload, contents)


if __name__ == "__main__":
    unittest.main()
