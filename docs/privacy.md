# Privacy: what is processed where

Measured on 2026-10-31 against the code in this repository. Where something was not checked, it says so.

## 1. Local processing (no data leaves the hub's own process or container)

- The analyser's static rules (`analyse_static`): a function over the text, no model, no network.
- The validator: runs the deliverable's own tests. Submitted code runs only where the network is cut off:
  a network namespace, or a worker container (`docker run --network none --read-only`) that confirmed
  its own isolation from the inside. If that cannot be confirmed, nothing is run. The report records
  which isolation held.
- The worker container is started without credentials; a credential-looking variable in its
  environment stops it (submitted code could read the worker's start-up environment).

## 2. Model provider (Anthropic API)

What goes to the provider: the material, the spec, the question, the chat message and the chat history,
after redaction (`hub/privacy.py`, using the analyser's `src.tools.redact`):

- secrets by pattern (hard-coded passwords and secrets, values only);
- card numbers by Luhn checksum. A long figure that is not a card (an order number, an epoch in
  milliseconds, a random sequence) is left as it was.

Rules that are enforced and tested (`apps/hub/tests/test_privacy_paths.py`, one set of values through every route):

- every text the client controls is redacted before it is put in a request, not only the material;
- redaction happens before the length limit, so a number cut by the limit is not left half-visible;
- if the redaction code is not available, nothing is sent and the answer says so;
- a provider's error text is redacted and cut before it is returned or logged.

Not covered: redaction is by pattern. A secret in a form the patterns do not know goes to the provider.
Names, addresses and free-text personal data are not redacted.

## 3. Reports and logs

For a material containing a card number, the run report, the fingerprint and the log output held no
card number (tested). The fingerprint names the material the client sent (its hash), not the redacted
text the model saw. What a stored run holds beyond the report was not audited here.

## 4. External code executors (not enabled)

No submitted code is sent to a hosted sandbox. This stays so until all of: a data-processing agreement,
explicit contract text about passing sources, tests and spec to the provider, a dedicated workspace with a
minimal key, a successful run on synthetic code, and confirmed deletion with a deny-all policy.
A synthetic probe of one provider's sandbox was run on 2026-10-31; no client code was involved.