from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("delivery_pipeline.py")
SPEC = importlib.util.spec_from_file_location("delivery_pipeline", MODULE_PATH)
assert SPEC and SPEC.loader
pipeline = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pipeline
SPEC.loader.exec_module(pipeline)


class DeliveryPipelineTests(unittest.TestCase):
    def test_package_validates(self) -> None:
        result = pipeline.validate()
        self.assertEqual(result["contracts"], 3)
        self.assertEqual(result["runtime_adapters"], 6)

    def test_public_scan_excludes_review_runtime(self) -> None:
        self.assertFalse(
            pipeline.is_public_package_path(
                pipeline.ROOT / ".revmux" / "tasks" / "review" / "report.md"
            )
        )
        self.assertFalse(
            pipeline.is_public_package_path(
                pipeline.ROOT / ".omc" / "state" / "session.json"
            )
        )
        self.assertTrue(
            pipeline.is_public_package_path(pipeline.ROOT / "references" / "case-state.md")
        )

    def test_generic_profile_is_safe(self) -> None:
        profile = pipeline.detect_profile(Path(tempfile.mkdtemp()))
        self.assertEqual(profile.profile_id, "generic")
        self.assertEqual(profile.capabilities, ("test",))

    def test_nearest_project_profile_wins(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            nested = root / "a" / "b"
            nested.mkdir(parents=True)
            profile_dir = root / ".delivery-engineering"
            profile_dir.mkdir()
            body = pipeline.PROFILE_TEMPLATE.read_text(encoding="utf-8").replace("profile_id: example", "profile_id: demo")
            (profile_dir / "profile.md").write_text(body, encoding="utf-8")
            profile = pipeline.detect_profile(nested)
            self.assertEqual(profile.profile_id, "demo")
            self.assertEqual(profile.project_root, root.resolve())

    def test_profile_rejects_unknown_capability(self) -> None:
        body = pipeline.PROFILE_TEMPLATE.read_text(encoding="utf-8").replace(
            "capabilities: backend,frontend,test", "capabilities: backend,ops,test"
        )
        with self.assertRaises(pipeline.PipelineError):
            pipeline.validate_profile_text(body, Path("profile.md"), allow_generic=False)


if __name__ == "__main__":
    unittest.main()
