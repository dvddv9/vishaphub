import re
import unittest
from pathlib import Path

from generator import __version__
from generator.config import PACKAGE_DIR, WEB_INDEX

ROOT = Path(__file__).resolve().parent.parent


class LayoutTests(unittest.TestCase):
    def test_the_folders_of_the_package(self):
        for d in ("api", "llm", "pipeline", "tools", "prompts", "web"):
            self.assertTrue((PACKAGE_DIR / d).is_dir(), d)
        for d in ("api", "llm", "pipeline", "tools"):
            self.assertTrue((PACKAGE_DIR / d / "__init__.py").is_file(), d)

    def test_no_old_flat_modules_are_left(self):
        for name in ("spec", "intake", "design", "build", "generate", "verify", "deliver",
                     "textcheck", "analyzer", "sarif", "examples", "server", "llm", "pipeline"):
            self.assertFalse((PACKAGE_DIR / f"{name}.py").exists(), name)

    def test_web_form_is_packaged(self):
        self.assertTrue(WEB_INDEX.is_file())

    def test_project_files_exist(self):
        for name in ("LICENSE", "README.md", "AGENTS.md", "SECURITY.md", "CHANGELOG.md",
                     "CONTRIBUTING.md", "Dockerfile", "docker-compose.yml", ".env.example",
                     ".dockerignore", ".gitignore", "ruff.toml", "requirements.txt",
                     "pyproject.toml", "run_tests.py", "run_local.ps1", "start_generator.bat",
                     ".pre-commit-config.yaml", ".github/workflows/ci.yml",
                     ".github/PULL_REQUEST_TEMPLATE.md", "deploy/README.md",
                     "docs/ARCHITECTURE.md", "docs/FAQ.md", "docs/LIMITATIONS.md",
                     "docs/ROADMAP.md", "docs/VISHAP.md", "docs/HISTORY.md"):
            self.assertTrue((ROOT / name).is_file(), name)


class VersionTests(unittest.TestCase):
    def test_version_is_the_same_everywhere(self):
        toml = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text("utf-8"), re.M)
        log = re.search(r"^## \[(\d[^\]]*)\]", (ROOT / "CHANGELOG.md").read_text("utf-8"), re.M)
        self.assertEqual(toml.group(1), __version__)
        self.assertEqual(log.group(1), __version__)

    def test_package_data_lists_prompts(self):
        self.assertIn("prompts/*.md", (ROOT / "pyproject.toml").read_text("utf-8"))


class SecretsTests(unittest.TestCase):
    def test_env_example_holds_no_key(self):
        text = (ROOT / ".env.example").read_text("utf-8")
        self.assertRegex(text, r"(?m)^CUSTOM_LLM_KEY=$")
        self.assertNotRegex(text, r"sk-[A-Za-z0-9]{10,}")


if __name__ == "__main__":
    unittest.main()
