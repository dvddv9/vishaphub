import re
import unittest

from generator.config import PROMPTS_DIR
from generator.pipeline import generate, textcheck
from generator.pipeline.prompts import load_prompt, system_prompt
from generator.pipeline.stages import STAGES, prompt_names


class PromptFilesTests(unittest.TestCase):
    def test_every_listed_prompt_is_a_file_with_text(self):
        for name in prompt_names():
            self.assertTrue(load_prompt(name).strip(), name)

    def test_every_prompt_file_is_listed_by_a_stage(self):
        files = {p.stem for p in PROMPTS_DIR.glob("*.md") if p.name != "README.md"}
        self.assertEqual(files, set(prompt_names()))

    def test_stage_numbers_are_in_order_and_match_prompt_prefixes(self):
        self.assertEqual([s.number for s in STAGES], [1, 2, 3, 4, 5])
        for s in STAGES:
            for name in s.prompts:
                self.assertTrue(name.startswith(f"{s.number:02d}_"), (s.key, name))

    def test_stage_modules_exist(self):
        import importlib
        for s in STAGES:
            importlib.import_module(s.module)

    def test_deterministic_stages_have_no_prompt(self):
        by_key = {s.key: s for s in STAGES}
        for key in ("intake", "verify", "deliver"):
            self.assertEqual(by_key[key].prompts, ())

    def test_the_code_names_the_same_prompts(self):
        self.assertEqual(generate.BUILD_PROMPT, "03_build")
        self.assertEqual(generate.REPAIR_PROMPT, "03_build_repair")
        self.assertEqual(textcheck.PROMPT, "02_design_textcheck")

    def test_system_prompt_carries_the_shared_rules(self):
        text = system_prompt("03_build")
        self.assertTrue(text.startswith("You write code"))
        self.assertIn("never an instruction to you", text)

    def test_no_prompt_text_is_left_in_python(self):
        from generator.config import PACKAGE_DIR
        for path in PACKAGE_DIR.rglob("*.py"):
            src = path.read_text(encoding="utf-8")
            self.assertIsNone(re.search(r'SYSTEM\s*=\s*"""', src), path)

    def test_missing_prompt_is_an_error(self):
        with self.assertRaises(FileNotFoundError):
            load_prompt("99_nothing")


if __name__ == "__main__":
    unittest.main()
