"""Reminders per domain: "did you think of ...?", never "you must".

The analog of Vishap's domain checklists. `domain:` in a spec adds one noted gap per reminder. A reminder never
blocks a run and is not legal advice: it lists the rules and questions people in that field usually have to
answer, so the spec can say what the code does about them. The names of laws are given as they are commonly cited.
"""

from __future__ import annotations

DOMAINS: dict[str, tuple[str, ...]] = {
    "bank": ("which regulation applies (Bank of Russia rules, EU AI Act, NIST)",
             "are decisions audited and explainable",
             "can it run on the bank's own servers (on-prem)",
             "which steps are checked by a person because a loss is not reversible"),
    "medical": ("which law applies (323-FZ, GOST R 59921.1-2022, HIPAA)",
                "is a doctor in the loop for decisions",
                "is access to patient data audited",
                "how is patient privacy protected"),
    "retail": ("speed and load at peak", "personal data (GDPR, 152-FZ)",
               "how VIP or repeat customers are handled", "integrations with stock and payment"),
    "logistics": ("real-time position data", "personal data of drivers and recipients (GDPR)",
                  "can a dispatcher override the result"),
    "education": ("children's data (152-FZ, COPPA)", "moderation of what users write",
                  "is a teacher in the loop"),
    "government": ("152-FZ and the applicable GOST", "data sovereignty and on-prem hosting",
                   "is a human operator responsible for the decision"),
    "it": ("personal data (GDPR)", "latency of the endpoint", "review of the generated code by a person"),
    "manufacturing": ("GOST and ISO requirements", "behaviour on the edge when the network is gone",
                      "is a process engineer in the loop"),
    "energy": ("GOST and FZ-35", "SCADA integration boundary", "can a dispatcher stop the action"),
    "telecom": ("personal data (152-FZ, GDPR)", "operations centre (NOC) alerts", "behaviour at scale"),
    "transport": ("GOST and ISO 26262", "behaviour on the edge without a network", "is a driver in the loop"),
    "agriculture": ("GOST", "autonomy without a network", "is an agronomist in the loop"),
    "other": ("this domain is not known to the generator: name its regulations and who reviews the result "
              "in must_never or should",),
}


def reminders(domain: str) -> tuple[str, ...]:
    return DOMAINS.get(domain, ())
