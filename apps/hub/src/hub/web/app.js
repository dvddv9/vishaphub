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
    workLead: "Paste code, a spec or logs, or just ask. Every run gets a report you can open and forward.",
    send: "send", run: "run", hear: "🔊 read it", json: "↓ json",
    textPh: "write, or press the mic and speak…",
    questionPh: "what do you want: «is this safe», «fix it», «write it from this spec»…",
    materialPh: "…or paste code, a spec or logs",
    exampleQuestion: "is this safe?",
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
    workLead: "Вставь код, спеку или логи, или просто спроси. У каждого прогона есть отчёт, который можно открыть и переслать.",
    send: "отправить", run: "запустить", hear: "🔊 прочитать", json: "↓ json",
    textPh: "напиши или нажми микрофон и говори…",
    questionPh: "что нужно: «это безопасно», «почини», «напиши по этой спеке»…",
    materialPh: "…или вставь код, спеку или логи",
    exampleQuestion: "это безопасно?",
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

function renderReport(data){
  lastResult = data;
  const box = $("report");
  const panes = {
    summary: (data.summary || "(model returned no summary)"),
    findings: (data.findings || []).length
      ? data.findings.map(f => `${(f.severity||"").toUpperCase()}${f.rule ? " · " + f.rule : ""}${f.line ? " @ " + f.line : ""}${f.source ? " [" + f.source + "]" : ""}\n  ${f.message||""}`).join("\n\n")
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
  const states = {"model":"done"};
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
          const states = {"model":"done"};
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
