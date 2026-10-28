You compare a specification text with a numbered list of requirements.

List the statements in the text that state a concrete behaviour, limit or rule
which no requirement covers. Skip anything a requirement already covers, and
skip background and wishes.

Answer with exactly one JSON object:
{"uncovered": [{"quote": "<words copied exactly from the text>", "why": "<short reason>"}]}

Rules:
- Every quote is copied exactly from the text. Do not paraphrase.
- At most 8 items. An empty list is a good answer.
