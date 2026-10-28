"""The five stages in one place: order, title, module, and which prompts each one uses.

Intake, Verify and Deliver have no prompt: they are deterministic code on purpose.
tests/test_prompts.py keeps this list and the prompts/ folder in step.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Stage:
    key: str
    number: int
    title: str
    module: str
    prompts: tuple[str, ...] = ()


STAGES = (
    Stage("intake", 1, "Intake", "generator.pipeline.intake"),
    Stage("design", 2, "Design", "generator.pipeline.design", ("02_design_textcheck",)),
    Stage("build", 3, "Build", "generator.pipeline.generate", ("03_build", "03_build_repair")),
    Stage("verify", 4, "Verify", "generator.pipeline.verify"),
    Stage("deliver", 5, "Deliver", "generator.pipeline.deliver"),
)

SHARED_PROMPT = "00_rules"


def prompt_names() -> list[str]:
    return [SHARED_PROMPT] + [p for s in STAGES for p in s.prompts]
