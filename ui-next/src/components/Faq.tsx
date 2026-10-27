const ITEMS: { q: string; a: string }[] = [
  {
    q: "What is FI (the fidelity index)?",
    a: "A score from 0 to 1 for how well the findings are backed. It averages four parts: evidence (were they checked by running Python), mechanism (does each finding carry a trace), grounding (does it name a CWE) and calibration (are level, priority and confidence consistent). It reads n/a when there are no findings to score, and rules-only runs have none.",
  },
  {
    q: "What does “stale” mean?",
    a: "Every report is valid for 90 days. After that it is marked stale: new CVEs, dependency advisories and your own code have moved on, so treat an old “no critical findings” as unproven and run the analysis again.",
  },
  {
    q: "What is a runbook?",
    a: "Incident steps per weakness (CWE): what to do immediately, in the short term and in the long term, and who to escalate to. The Runbook tab comes from a fixed table, so it is the same every time; the written report may add fix steps from the model.",
  },
  {
    q: "Do I need an API key?",
    a: "No. The public demo runs on the server's own model. A daily limit applies to each visitor and to the whole demo, so it can run out for the day; try again tomorrow.",
  },
  {
    q: "What happens to my code?",
    a: "It is sent to this server and on to its language-model provider to produce the report. Jobs are held in the server's memory and disappear on a restart; the report stays in this browser. Do not paste secrets you cannot rotate.",
  },
];

/** Five short answers, collapsed by default. */
export default function Faq() {
  return (
    <section aria-labelledby="faq" className="mt-10 w-full pb-4">
      <h2 id="faq" className="text-lg font-medium text-slate-900">
        Questions
      </h2>
      <div className="mt-4 divide-y divide-slate-200 rounded-xl border border-slate-200 bg-white shadow-sm">
        {ITEMS.map((item) => (
          <details key={item.q} className="group px-4 py-3">
            <summary className="flex min-h-9 cursor-pointer list-none items-center justify-between gap-3 text-sm font-medium text-slate-900 [&::-webkit-details-marker]:hidden">
              {item.q}
              <span
                aria-hidden="true"
                className="font-mono text-slate-500 transition-transform group-open:rotate-45"
              >
                +
              </span>
            </summary>
            <p className="mt-2 text-sm leading-relaxed text-slate-600">{item.a}</p>
          </details>
        ))}
      </div>
    </section>
  );
}
