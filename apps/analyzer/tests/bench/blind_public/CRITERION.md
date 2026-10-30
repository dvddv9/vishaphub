# The quality barrier before a pilot, written before the data

This file and `criterion.json` were committed before any blind example was fetched or scored. The numbers are
the author's choice and the reader may disagree with them; what matters is that they were fixed first.

## What SAFE means

A hub verdict of **SAFE** means exactly this: for the language of the submitted text, the hub's rules have been
**measured** against an independently labelled blind set and passed the gates below; the text is **covered**
(language recognised, no line cut, no scan error); and the rules **found nothing** in it.

It is not a claim that the code has no vulnerabilities. It says nothing about classes of defect the rules do not
look for (authorization, business logic, dependencies, configuration at runtime), and the report lists what was not
checked.

Everything else is **REQUIRES_REVIEW**: any finding, of any severity; a language that is not measured or that
failed its gates (*unknown coverage*); a text the scanner could not read in full.

## The gates, per language

A language is **measured** with at least 20 dangerous and 20 safe examples in the blind set. Below that it is
unmeasured and SAFE is never issued for it.

* **G1** - no example labelled critical gets SAFE. Zero tolerated.
* **G2** - the false-SAFE rate (a dangerous example, of any criticality, that got SAFE) must have a **95% Wilson
  upper bound of at most 20%**. The upper bound, not the point estimate, so that a small set cannot pass by luck:
  0 of 20 passes (upper 16.1%), 1 of 20 does not (upper 23.6%).

`safe_allowed(language)` = measured and G1 and G2. The hub reads it; nothing else turns SAFE on.

Reported, not gating: the review burden (how many safe examples were *not* called SAFE), false-SAFE per criticality,
time.

## The model in the loop

The same sample, **3 runs per example** (the model is not deterministic), gates **M1** (no critical example gets SAFE
in any run) and **M2** (false-SAFE upper bound at most 20%). It is paid, so it does not run in CI; its committed
result is required before a pilot, and SAFE with a model is claimed only for the languages where it passed.

## How the blind set is kept blind

* **Independent labels.** They come from the source's own ground truth: an expected-results file, a vulnerable /
  secure pair, the source's own test expectations. Never from this repository's rules, never from the author of
  this repository.
* **Frozen.** The ids are hashed in `frozen_ids.sha256` before the first scoring. An example added later is marked
  `post_run: true` and reported apart; it is never counted in a gate.
* **No tuning on the answers.** A rule written after a blind result is written for the *class* of defect. The
  examples that prompted it stay in the set and stay counted.
* **Human sample.** Before a pilot, a person who is not the author labels a small sample of the team's real code
  (or its anonymised stand-in) for each language the team uses. The labels are a CSV and are scored by the same
  code.

## What is not claimed

Precision on real code, recall beyond the classes in the sources, anything about languages with no blind set, and
anything about the model until its own run exists.
