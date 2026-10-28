"""No-network smoke checks for standalone deployment packaging."""
import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

class PackagingTests(unittest.TestCase):
    def test_manager_syntax(self):
        ast.parse((ROOT / "manage.py").read_text())

    def test_no_supervisor_dependency(self):
        for name in ("manage.py", "compose.yaml", "Dockerfile"):
            source = (ROOT / name).read_text()
            self.assertNotIn("SUPERVISOR_TOKEN", source)
            self.assertNotIn("http://supervisor", source)
            self.assertNotIn("bashio::", source)

    def test_private_defaults(self):
        compose = (ROOT / "compose.yaml").read_text()
        self.assertIn("127.0.0.1}:8554", compose)
        self.assertIn("127.0.0.1:8788:8788", compose)
        self.assertIn("no-new-privileges:true", compose)

    def test_required_auth(self):
        source = (ROOT / "manage.py").read_text()
        self.assertIn("WEB_PASSWORD", source)
        self.assertIn("secrets.compare_digest", source)
        self.assertIn('if not self.check():', source)
        self.assertNotIn('"url": job["payload"]', source)

if __name__ == "__main__":
    unittest.main()
