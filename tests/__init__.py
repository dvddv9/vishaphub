"""The suite does not run the mutation check by default (it adds a run per mutant to every pipeline test); the
tests of the check itself ask for it with an explicit number."""

import os

os.environ.setdefault("GENERATOR_MUTANTS", "0")
