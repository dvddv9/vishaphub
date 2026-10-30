// Two languages, because the first client may not read English, and a product that
// cannot say "what I did not check" in his language is a product he cannot use.
const I18N = {
  en: {
    title: "Carry the request.<br><em>Prove</em> the result.",
    lead: "Paste code, a spec or logs. I route it: the generator writes code from the spec, the validator checks it against that spec, the analyser checks whether it is dangerous. I ask only what is missing and return what the pipeline said.",
    meta: "3 stages · 6 validator checks · strictest verdict wins · audit trail",
    try: "Try with an example", talk: "Talk to Vishap", recent: "recent runs",
    navHow: "How it works", navWork: "Try it",
    howEyebrow: "how it works", howTitle: "One plan, three jobs, one verdict",
    s1t: "Generate", s1p: "The model proposes code from your spec. It proposes; it never decides.",
    s2t: "Validate", s2p: "Six checks compare the code with the promise: structure, syntax, contract, coverage, behavior, conformance.",
    s3t: "Analyse", s3p: "The analyser checks whether the code is dangerous. Every finding is named, with its source.",
    howFoot: "The strictest verdict wins. Whatever was not checked is listed, not hidden.",
    workEyebrow: "workbench", workTitle: "Try it on your own code",
    workLead: "Paste code, a spec or logs below and press run. You get a verdict, what is wrong and how to fix it, and a report you can forward.",
    send: "send", run: "run", hear: "🔊 read it", json: "↓ json",
    textPh: "write, or press the mic and speak…",
    questionPh: "optional: what you want to know, e.g. “is this safe?” or “fix it”",
    materialPh: "e.g. paste something like this:\n\n@app.get(\"/user\")\ndef user():\n    name = request.args.get(\"name\", \"\")\n    cur.execute(f\"select * from users where name = '{name}'\")",
    exampleQuestion: "is this safe?",
    sampleBtn: "paste a sample and run",
    keySys: "The hub holds no model key. The rules check your code for free; to have the model read it too, add your own Anthropic key below (it stays in this browser).",
    keyHint: "Optional. Without a key only the rules run; with your key the model reads the code as well, and the stricter verdict wins. The key is kept in this browser and sent with your run.",
    noModelSummary: "No model read this run, so there is no model summary. The rules found {n} finding(s): open FINDINGS. Add your own key below to have the model read the code too.",
    verdictHint: "REQUIRES_REVIEW means a person should read the findings. The hub does not issue SAFE yet: its rules are not measured well enough for any language.",
    working: "working…", nothing: "nothing to work on", refused: "refused",
    verdictLabel: "verdict", notChecked: "not checked", openReport: "open the report",
    reportAt: "run", copy: "copy", copied: "copied", noAccess: "no access",
    micOff: "this browser has no speech input; Chrome and Edge do",
    micNo: "microphone refused or unavailable",
    savedKey: "key saved in this browser", clearedKey: "key cleared",
    streamLost: "the stream ended without a verdict",
    truncated: "…the answer was cut by the token limit; ask to continue if it matters"
  },
  ru: {
    title: "Принять запрос.<br><em>Доказать</em> результат.",
    lead: "Вставь код, спеку или логи. Я разложу: генератор напишет код по спеке, валидатор сверит его со спекой, анализатор проверит, опасно ли. Спрошу только то, чего не хватает, и верну то, что сказал конвейер.",
    meta: "3 стадии · 6 проверок валидатора · побеждает строжайший вердикт · след прогона",
    try: "Показать на примере", talk: "Поговорить с Vishap", recent: "последние прогоны",
    navHow: "Как это работает", navWork: "Попробовать",
    howEyebrow: "как это работает", howTitle: "Один план, три задачи, один вердикт",
    s1t: "Сгенерировать", s1p: "Модель предлагает код по твоей спеке. Она предлагает, но не решает.",
    s2t: "Сверить", s2p: "Шесть проверок сравнивают код с обещанием: структура, синтаксис, контракт, покрытие, поведение, соответствие.",
    s3t: "Проанализировать", s3p: "Анализатор проверяет, не опасен ли код. Каждая находка названа вместе с источником.",
    howFoot: "Побеждает строжайший вердикт. Что не проверено, то перечислено, а не спрятано.",
    workEyebrow: "рабочий стол", workTitle: "Попробуй на своём коде",
    workLead: "Вставь код, спеку или логи ниже и нажми «запустить». Получишь вердикт, что не так и как исправить, и отчёт, который можно переслать.",
    send: "отправить", run: "запустить", hear: "🔊 прочитать", json: "↓ json",
    textPh: "напиши или нажми микрофон и говори…",
    questionPh: "по желанию: что хочешь узнать, например «это безопасно?» или «почини»",
    materialPh: "например, вставь что-то такое:\n\n@app.get(\"/user\")\ndef user():\n    name = request.args.get(\"name\", \"\")\n    cur.execute(f\"select * from users where name = '{name}'\")",
    exampleQuestion: "это безопасно?",
    sampleBtn: "вставить пример и запустить",
    keySys: "У хаба нет ключа модели. Правила проверяют код бесплатно; чтобы код читала ещё и модель, добавь свой ключ Anthropic ниже (он остаётся в этом браузере).",
    keyHint: "Не обязательно. Без ключа работают только правила; с твоим ключом код читает ещё и модель, и побеждает более строгий вердикт. Ключ хранится в этом браузере и уходит вместе с твоим запуском.",
    noModelSummary: "\u042d\u0442\u0443 \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0443 \u043d\u0435 \u0447\u0438\u0442\u0430\u043b\u0430 \u043c\u043e\u0434\u0435\u043b\u044c, \u043f\u043e\u044d\u0442\u043e\u043c\u0443 \u0441\u0432\u043e\u0434\u043a\u0438 \u043c\u043e\u0434\u0435\u043b\u0438 \u043d\u0435\u0442. \u041f\u0440\u0430\u0432\u0438\u043b\u0430 \u043d\u0430\u0448\u043b\u0438 \u043d\u0430\u0445\u043e\u0434\u043e\u043a: {n}. \u041e\u0442\u043a\u0440\u043e\u0439 \u0432\u043a\u043b\u0430\u0434\u043a\u0443 findings. \u0414\u043e\u0431\u0430\u0432\u044c \u0441\u0432\u043e\u0439 \u043a\u043b\u044e\u0447 \u043d\u0438\u0436\u0435, \u0447\u0442\u043e\u0431\u044b \u043a\u043e\u0434 \u043f\u0440\u043e\u0447\u0438\u0442\u0430\u043b\u0430 \u0435\u0449\u0451 \u0438 \u043c\u043e\u0434\u0435\u043b\u044c.",
    verdictHint: "REQUIRES_REVIEW значит: человеку стоит прочитать находки. SAFE хаб пока не выдаёт: его правила не измерены достаточно хорошо ни для одного языка.",
    working: "работаю…", nothing: "нечего проверять", refused: "отказ",
    verdictLabel: "вердикт", notChecked: "не проверено", openReport: "открыть отчёт",
    reportAt: "прогон", copy: "копировать", copied: "скопировано", noAccess: "нет доступа",
    micOff: "в этом браузере нет распознавания речи; есть в Chrome и Edge",
    micNo: "микрофон недоступен или отклонён",
    savedKey: "ключ сохранён в этом браузере", clearedKey: "ключ стёрт",
    streamLost: "поток закончился без вердикта",
    truncated: "…ответ обрезан лимитом токенов; если важно — попроси продолжить"
  }
};
let lang = localStorage.getItem("vishap_lang")
  || ((navigator.language || "en").toLowerCase().startsWith("ru") ? "ru" : "en");

function t(key){
  const table = I18N[lang] || I18N.en;
  return table[key] !== undefined ? table[key] : (I18N.en[key] || key);
}

function applyLang(){
  document.documentElement.lang = lang;
  document.querySelectorAll("[data-i18n]").forEach(el => { el.textContent = t(el.dataset.i18n); });
  document.querySelectorAll("[data-i18n-html]").forEach(el => { el.innerHTML = t(el.dataset.i18nHtml); });
  document.querySelectorAll("[data-i18n-ph]").forEach(el => { el.placeholder = t(el.dataset.i18nPh); });
  const btn = document.getElementById("lang");
  if (btn) btn.textContent = lang === "ru" ? "EN" : "RU";
}

const $ = (id) => document.getElementById(id);
const chat = $("chat");
const voiceOn = {v:false};
const history = [];

function bubble(role, text){
  const div = document.createElement("div");
  div.className = "msg " + (role === "user" ? "me" : role === "assistant" ? "him" : "sys");
  div.textContent = text;
  chat.appendChild(div); chat.scrollTop = chat.scrollHeight;
  return div;
}

async function sayText(text){
  if (!text) return;
  try {
    const res = await fetch("/speak", {method:"POST", headers:{"content-type":"application/json"},
      body: JSON.stringify({text})});
    if (!res.ok) return;
    const blob = await res.blob();
    await new Audio(URL.createObjectURL(blob)).play().catch(()=>{});
  } catch (e) { /* silence beats a modal here */ }
}

$("say").onclick = () => {
  voiceOn.v = !voiceOn.v;
  $("say").setAttribute("aria-pressed", String(voiceOn.v));
  $("say").textContent = voiceOn.v ? "♪ voice on" : "▶ hear me";
  if (voiceOn.v) {
    const a = $("voice"); a.currentTime = 0; a.play().catch(()=>{});
  } else {
    $("voice").pause();
  }
};
$("focusComposer").onclick = () => $("text").focus();
$("tryExample").onclick = () => {
  $("material").value = "cur.execute(\"select * from users where name = '\" + name + \"'\")";
  $("question").value = t("exampleQuestion");
  pipeline();
};

$("sampleRun").onclick = $("tryExample").onclick;

$("save").onclick = () => { localStorage.setItem("vishap_key", $("key").value.trim()); bubble("sys", t("savedKey")); };
$("clear").onclick = () => { localStorage.removeItem("vishap_key"); $("key").value=""; bubble("sys", t("clearedKey")); };
$("key").value = localStorage.getItem("vishap_key") || "";

async function ask(message){
  if (!message.trim()) return;
  bubble("user", message);
  history.push({role:"user", content:message});
  const thinking = bubble("sys", "…");
  try {
    const res = await fetch("/chat", {method:"POST", headers:{"content-type":"application/json"},
      body: JSON.stringify({message, messages: history, api_key: localStorage.getItem("vishap_key") || ""})});
    const data = await res.json();
    thinking.remove();
    if (!data.ok){ bubble("sys", data.error || "failed"); return; }
    // A truncated answer is shown, but never as a whole one: the mark is the difference
    // between «it stopped there» and «it said everything».
    bubble("assistant", data.truncated ? `${data.text}\n\n${t("truncated")}` : data.text);
    history.push({role:"assistant", content:data.text});
    if (voiceOn.v) sayText(data.text);
  } catch (e) { thinking.remove(); bubble("sys", e.message); }
}

$("send").onclick = () => { const line = $("text").value; $("text").value=""; ask(line); };
$("text").addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey){ e.preventDefault(); $("send").click(); } });
document.querySelectorAll(".chip").forEach(c => c.onclick = () => ask(c.dataset.q));

$("drop").onclick = () => $("picker").click();
$("drop").addEventListener("keydown", e => {
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("picker").click(); }
});
$("picker").onchange = async (e) => {
  const f = e.target.files && e.target.files[0];
  if (!f) return;
  $("material").value = await f.text();
  bubble("sys", `loaded ${f.name} (${$("material").value.length} chars)`);
};
["dragenter","dragover"].forEach(ev => $("drop").addEventListener(ev, e => { e.preventDefault(); $("drop").classList.add("hot"); }));
["dragleave","drop"].forEach(ev => $("drop").addEventListener(ev, e => { e.preventDefault(); $("drop").classList.remove("hot"); }));
$("drop").addEventListener("drop", async e => {
  const f = e.dataTransfer.files && e.dataTransfer.files[0];
  if (!f) return;
  $("material").value = await f.text();
  bubble("sys", `loaded ${f.name} (${$("material").value.length} chars)`);
});

const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
const micOn = (state) => {
  $("mic").classList.toggle("on", state);
  $("mic").setAttribute("aria-pressed", String(state));
};
$("mic").onclick = () => {
  if (!Recognition){ bubble("sys", t("micOff")); return; }
  const r = new Recognition(); r.lang = lang === "ru" ? "ru-RU" : "en-US"; r.interimResults = false; r.maxAlternatives = 1;
  micOn(true);
  r.onresult = (e) => { const said = e.results[0][0].transcript; micOn(false); ask(said); };
  r.onerror = () => { micOn(false); bubble("sys", t("micNo")); };
  r.onend = () => micOn(false);
  r.start();
};

let lastSpoken = "";

let lastResult = null;

function groupFindings(list, fn){
  const own = list.filter(f => !f.in_patch), pat = list.filter(f => f.in_patch);
  return [...own.map(fn), ...(pat.length ? ["IN THE MODEL'S PATCH (line numbers refer to the patch)"] : []), ...pat.map(fn)];
}

function renderReport(data){
  lastResult = data;
  const box = $("report");
  const ag = data.agreement || {};
  const head = Object.keys(ag).length
    ? `seen by both readers: ${ag.both} \u00b7 model only: ${ag.model_only} \u00b7 rules only: ${ag.rules_only}${ag.in_patch ? " \u00b7 in the model's patch: " + ag.in_patch : ""}\n\n`
    : "";  const panes = {
    summary: data.summary
      ? (data.model ? "MODEL SUMMARY" + (Object.keys(data.patch || {}).length ? " (the hub did not run the patch)" : "") + "\n\n" : "") + data.summary
      : (data.model ? "(model returned no summary)" : t("noModelSummary").replace("{n}", String((data.findings || []).length))),
    findings: (data.findings || []).length
      ? head + groupFindings(data.findings, f => {
        const by = (f.seen_by || []).length > 1 ? "rules + model" : (f.source || "");
        return `${(f.severity||"").toUpperCase()}${f.rule ? " \u00b7 " + f.rule : ""}${f.line ? " @ " + f.line : ""}${by ? " [" + by + "]" : ""}\n  ${f.message||""}${f.fix ? "\n  fix: " + f.fix : ""}${f.possibly_covered_by ? "\n  possibly covered by " + f.possibly_covered_by : ""}`;
      }).join("\n\n")
      : "nothing matched",
    patch: Object.keys(data.patch || {}).length
      ? Object.entries(data.patch).map(([n, c]) => `── ${n} ──\n${c}`).join("\n\n")
      : "no patch proposed",
    proof: (data.proof || []).length ? data.proof.map(p => "- " + p).join("\n") : "no proof lines",
    [t("notChecked")]: (data.not_checked || []).length
      ? "• " + (data.not_checked || []).join("\n• ")
      : "everything this plan covers was checked",
  };
  const names = Object.keys(panes);
  const fp = data.fingerprint || {};
  const reportLink = fp.id
    ? `<a href="/r/${encodeURIComponent(fp.id)}" target="_blank" rel="noopener"
         class="report-link">${escapeHtml(t("openReport"))} ↗</a>`
    : "";
  box.innerHTML = `<div class="tabs">` + names.map((n, i) =>
      `<span class="tab ${i===0?"on":""}" data-pane="${escapeHtml(n)}">${escapeHtml(n)}</span>`).join("")
    + `<span class="copy" id="copy">${escapeHtml(t("copy"))}</span></div>
    <div class="pane" id="pane"></div>
    <div class="report-meta">
      ${fp.id ? `<span>${escapeHtml(t("reportAt"))} <code>${escapeHtml(fp.id)}</code></span>` : ""}
      ${reportLink}
    </div>
    <div id="qs"></div>`;

  const setPane = (name) => {
    $("pane").textContent = panes[name] || "";
  };
  setPane(names[0]);
  box.querySelectorAll(".tab").forEach(tab => tab.onclick = () => {
    box.querySelectorAll(".tab").forEach(x => x.classList.remove("on"));
    tab.classList.add("on");
    setPane(tab.dataset.pane);
  });
  $("copy").onclick = async () => {
    const text = $("pane").textContent;
    try { await navigator.clipboard.writeText(text); $("copy").textContent = t("copied"); }
    catch (e) { $("copy").textContent = t("noAccess"); }
    setTimeout(() => { $("copy").textContent = t("copy"); }, 1400);
  };

  const qs = data.questions || [];
  if (qs.length){
    $("qs").innerHTML = `<div class="qs-label">the model needs an answer:</div>`
      + qs.map((q, i) => `<span class="q" data-q="${escapeHtml(q)}">${escapeHtml(q)}</span>`).join("");
    $("qs").querySelectorAll(".q").forEach(el => el.onclick = () => ask(el.dataset.q));
  }
}

function escapeHtml(s){
  return String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}

function setProgress(states){
  const names = ["model", "rules", "validator", "verdict"];
  $("progress").innerHTML = names.map(n =>
    `<span class="step ${states[n]||""}"><span class="b"></span>${n}</span>`).join("");
}

function showResult(data, started){
  if (!data.ok){
    setProgress({"model":"fail"});
    $("verdict").innerHTML = `<b>${escapeHtml(t("refused"))}</b> ${escapeHtml(data.error || "failed")}`;
    if (data.fingerprint && data.fingerprint.id) renderReport(data);
    return;
  }

  const checks = data.checks || {};
  const states = {"model": checks.generator ? "done" : ""};
  if (checks.analyser) states.rules = "done";
  if (checks.validator) states.validator = "done";
  states.verdict = /SAFE|PASS/i.test(data.verdict) ? "done" : "fail";
  setProgress(states);

  const bits = [];
  if (checks.generator) bits.push(`generator <b>${escapeHtml(checks.generator.verdict)}</b>`);
  if (checks.analyser) bits.push(`analyser <b>${escapeHtml(checks.analyser.verdict)}</b>`);
  if (checks.validator) bits.push(`validator <b>${escapeHtml(checks.validator.verdict)}</b>`);
  const secs = ((performance.now() - started) / 1000).toFixed(1);
  $("verdict").innerHTML = `${escapeHtml(t("verdictLabel"))} <b>${escapeHtml(data.verdict)}</b>`
    + (bits.length ? " · " + bits.join(" · ") : "")
    + ` <span class="dim">· ${secs}s</span>`;

  $("verdict").dataset.v = data.verdict || "";
  renderReport(data);
  $("cardVerdict").textContent = data.verdict || "—";
  $("cardVerdict").dataset.v = data.verdict || "";
  const doneCount = [checks.analyser, checks.validator].filter(Boolean).length + 1;
  $("cardChecks").textContent = `${doneCount} of 3`;
  $("cardFindings").textContent = String((data.findings || []).length);
  $("cardTag").textContent = "live";
  $("hear").disabled = false;
  $("download").disabled = false;

  lastSpoken = `${data.summary || ""} ${t("verdictLabel")}: ${data.verdict}.`;
  if (voiceOn.v) sayText(lastSpoken);
}

async function pipeline(){
  const material = $("material").value;
  const question = $("question").value;
  if (!material.trim() && !question.trim()){ $("verdict").innerHTML = `<b>${escapeHtml(t("nothing"))}</b>`; return; }

  const started = performance.now();
  $("verdict").dataset.v = ""; $("verdict").textContent = t("working");
  $("report").innerHTML = "";
  $("hear").disabled = true;
  $("download").disabled = true;
  setProgress({"model":"run"});

  const wake = setTimeout(() => { $("waking").style.display = "block"; }, 8000);
  const body = JSON.stringify({material, question, spec: "",
                               api_key: localStorage.getItem("vishap_key") || ""});
  const clearWake = () => { clearTimeout(wake); $("waking").style.display = "none"; };

  // The run is announced stage by stage: a minute of silence reads as broken.
  try {
    const res = await fetch("/run/stream", {method:"POST",
      headers:{"content-type":"application/json"}, body});
    const isStream = res.ok && res.body && (res.headers.get("content-type") || "").includes("event-stream");
    if (!isStream) {
      const plain = await fetch("/run", {method:"POST", headers:{"content-type":"application/json"}, body});
      clearWake();
      showResult(await plain.json(), started);
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let done = null;
    let modelSeen = false;
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) break;
      buffer += decoder.decode(chunk.value, {stream: true});
      const parts = buffer.split("\n\n");
      buffer = parts.pop() || "";
      for (const part of parts) {
        let name = "", payload = "";
        for (const line of part.split("\n")) {
          if (line.startsWith("event: ")) name = line.slice(7).trim();
          else if (line.startsWith("data: ")) payload += line.slice(6);
        }
        if (!payload) continue;
        let data = null;
        try { data = JSON.parse(payload); } catch (e) { continue; }
        if (name === "stage"){
          if (data.stage === "generator") modelSeen = true;
          const states = {"model": modelSeen ? "done" : ""};
          if (data.stage === "validator") states.validator = "done";
          if (data.stage === "analyser") states.rules = "done";
          setProgress(states);
        }
        if (name === "done") done = data;
        if (name === "error") done = {ok:false, error:data.error};
      }
    }
    clearWake();
    if (done) showResult(done, started);
    else {
      setProgress({"model":"fail"});
      $("verdict").innerHTML = `<b>error</b> ${escapeHtml(t("streamLost"))}`;
    }
  } catch (e) {
    clearWake();
    setProgress({"model":"fail"});
    $("verdict").innerHTML = `<b>error</b> ${escapeHtml(e.message)}`;
  }
}

$("run").onclick = pipeline;
$("hear").onclick = () => sayText(lastSpoken);
$("download").onclick = () => {
  if (!lastResult) return;
  const blob = new Blob([JSON.stringify(lastResult, null, 2)], {type:"application/json"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "vishap-report.json";
  a.click();
  URL.revokeObjectURL(a.href);
};

setProgress({});
applyLang();
$("lang").onclick = () => {
  lang = lang === "ru" ? "en" : "ru";
  localStorage.setItem("vishap_lang", lang);
  applyLang();
};
fetch("/health").then(r=>r.json()).then(d=>{$("ver").textContent = d.version;}).catch(()=>{});
