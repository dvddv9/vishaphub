# Prompts

The model is called in three places; each has its own file. The file is the whole prompt:
the code adds only the data (spec text, requirements, problems) in the user message.

| File | Stage | Used by |
|---|---|---|
| `00_rules.md` | all | appended to every system prompt |
| `02_design_textcheck.md` | 2 Design | `pipeline/textcheck.py` — free text against the numbered requirements (report only) |
| `03_build.md` | 3 Build | `pipeline/generate.py` — write the files |
| `03_build_repair.md` | 3 Build | `pipeline/generate.py` — fix them after Verify (user message, not system) |

Intake (1), Verify (4) and Deliver (5) have no prompt on purpose: they are deterministic code,
so their verdicts do not depend on a model.

Data from the user goes between random `VG_<LABEL>_<hex>` markers (`pipeline/prompts.py`), so
text inside a spec cannot close the block and pass for instructions.
