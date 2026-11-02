// Two languages, because the first client may not read English, and a product that
// cannot say "what I did not check" in his language is a product he cannot use.
const I18N = {
  en: {
    title: "Carry the request.<br><em>Prove</em> the result.",
    lead: "Paste code, a spec or logs. I screen supplied code, generate from the spec, screen and validate the result, return a corrected version, validate it, then generate a final version clearly marked as not re-verified.",
    meta: "private analysis · Creator correction checked against the spec · final version is clearly marked · audit trail",
    try: "Try with an example", recent: "recent runs",
    navHow: "How it works", navWork: "Try it",
    howEyebrow: "how it works", howTitle: "One plan, seven stages, one verdict",
    s1t: "Analyse input", s1p: "Screen the code and files you supplied before generation.",
    s2t: "Generate", s2p: "The model proposes code from your spec. It proposes; it never decides.",
    s3t: "Analyse output", s3p: "Screen the generated code. Findings from both scans are kept.",
    s4t: "Validate", s4p: "Six checks compare the generated code with the promise: structure, syntax, contract, coverage, behavior, conformance.",
    s5t: "Creator / corrected version", s5p: "Creator returns complete corrected files using the findings and original spec.",
    s6t: "Validate the correction", s6p: "Validator runs the six checks again against Creator's corrected files and the same spec.",
    s7t: "Final generator", s7p: "Generate the final complete version after validation. It is delivered clearly as not re-verified.",
    correctedVersion: "Corrected version (checked after Creator)", finalVersion: "Final generator version (not re-verified)",
    howFoot: "The strictest verdict wins. Whatever was not checked is listed, not hidden.",
    workEyebrow: "workbench", workTitle: "Try it on your own code",
    workLead: "Paste code, a spec or logs below and press run. You get a verdict, what is wrong and how to fix it, and a report you can forward.",
    send: "send", run: "run", hear: "🔊 read it", json: "↓ json",
    textPh: "write, or press the mic and speak…",
    questionPh: "optional: what you want to know, e.g. “is this safe?” or “fix it”",
    materialPh: "e.g. paste something like this:\n\n@app.get(\"/user\")\ndef user():\n    name = request.args.get(\"name\", \"\")\n    cur.execute(f\"select * from users where name = '{name}'\")",
    exampleQuestion: "is this safe?",
    sampleBtn: "Load example",
    keySys: "The hub holds no model key. The rules check your code for free; to have the model read it too, add a key below: Anthropic, DeepSeek or ChatGPT (Ollama needs none; the key stays in this browser).",
    chooseProject: "choose project folder",
    chooseFile: "Choose an existing code file",
    fileNote: "the file is read in this browser and sent with your run",
    runEyebrow: "secure code workflow",
    runTitle: "Run the full pipeline",
    runIntro: "Choose a mode, add your code and specification, then review the report and the corrected version's final validation.",
    modeLabel: "Run mode",
    modeFull: "Full pipeline",
    modeGenerate: "Generate + validate",
    modeAnalyse: "Analyse only",
    materialLabel: "Existing code or files",
    specLabel: "Specification: what should the code do?",
    specPh: "Describe expected behavior and constraints",
    questionLabel: "Optional instructions for the model",
    fullFlowHint: "For all seven stages and a validated corrected version, provide both existing code/files and a specification. A specification alone runs generation and validation.",
    stageInput: "input scan", stageGenerate: "generate", stageOutput: "output scan",
    stageValidate: "validate", stageCreator: "Creator", stageFinalValidate: "validate fix", stageFinalGenerate: "final generate",
    modelTitle: "Model connection",
    modelHint: "Generation and Creator need a model. Your key stays in this browser and is sent with the run. Ollama needs no key.",
    providerLabel: "Provider",
    modelNameLabel: "Model name (optional)",
    modelNamePh: "Optional model name",
    apiKeyLabel: "API key",
    apiKeyPh: "Paste your provider key",
    save: "Save key",
    clear: "Clear key",
    projectEmpty: "No project files loaded.",
    projectHint: "Folder scans use Vishap's static rules only. Files go to the VishapHub service, not to your model provider. Up to 200 text files / 500,000 characters; generated, binary and obvious credential files or values are skipped.",
    projectLoaded: "{files} files · {chars} characters{skipped}",
    projectSkipped: " · {n} generated, binary or credential files/values skipped",
    projectNoText: "No readable text files found.",
    projectTooMany: "Choose at most 200 text files. The previous selection was cleared.",
    projectTooLarge: "Selected source exceeds 500,000 characters. The previous selection was cleared.",
    projectReadError: "A selected file could not be read as text. The previous selection was cleared.",
    projectQuestionBlocked: "Folder scans use rules only and do not send files to a model. Clear selected files to ask a model about pasted code.",
    projectInputConflict: "Folder scans accept only the selected files. Clear the code, specification and model instructions first.",
    projectDuplicate: "Two selected files have the same relative path: {path}. Choose a single project folder.",
    fullNeedsCodeSpec: "The full pipeline needs both existing code and a specification.",
    specRequired: "Add a specification for this mode.",
    analyseNeedsCode: "Add code or select a project folder to analyse.",
    analyseStaticOnly: "Analyse mode uses static rules only. Clear the specification and model instructions, or choose a generation mode.",
    keyHint: "Optional. Without a key only the rules run; with your key and a question the model reads the code as well, and the stricter verdict wins. The key is kept in this browser and sent with your run.",
    noModelSummary: "No model read this run, so there is no model summary. The rules found {n} finding(s): open FINDINGS. Add your own key below to have the model read the code too.",
    verdictHint: "REQUIRES_REVIEW means a person should read the findings. Rules-only SAFE is currently eligible for Java after a complete scan with no findings; other languages remain in review.",
    working: "working…", nothing: "nothing to work on", refused: "refused",
    verdictLabel: "verdict", notChecked: "not checked", openReport: "open the report",
    statRisk: "risk verdict", statFix: "fix", statVerify: "verification",
    reportAt: "run", copy: "copy", copied: "copied", noAccess: "no access",
    micOff: "this browser has no speech input; Chrome and Edge do",
    micNo: "microphone refused or unavailable",
    savedKey: "key saved in this browser", clearedKey: "key cleared",
    streamLost: "the stream ended without a verdict",
    truncated: "…the answer was cut by the token limit; ask to continue if it matters",
    modeHint: "The full flow uses both code and a specification. Analysis-only scans code with static rules.",
    keyRequired: "Add an API key for the selected provider, or choose Ollama.",
    creatorRescan: "Rescan Creator files with static rules",
    creatorRescanBusy: "Scanning the exact Creator files…",
    creatorRescanHint: "This checks the proposed files with Vishap's static rules only. It does not run tests or verify runtime behavior.",
    creatorRescanDone: "Static rescan complete: {n} finding(s). No tests or runtime checks were run.",
    creatorRescanFailed: "Static rescan could not be completed: {error}",
    creatorRescanReport: "Open static rescan report",
    paletteLabel: "Color palette",
    paletteBalanced: "Balanced",
  },
  ru: {
    title: "Принять запрос.<br><em>Доказать</em> результат.",
    lead: "Вставь код, спеку или логи. Сначала я проверю исходный код, затем сгенерирую и проверю результат, попрошу Creator исправить его, проверю исправление и соберу финальную версию с явной пометкой о неповторной проверке.",
    meta: "закрытый анализ · исправление Creator проходит повторную проверку · финальная версия помечена явно · след прогона",
    try: "Показать на примере", recent: "последние прогоны",
    navHow: "Как это работает", navWork: "Попробовать",
    howEyebrow: "как это работает", howTitle: "Один план, семь стадий, один вердикт",
    s1t: "Проверить вход", s1p: "До генерации проверяется присланный код и файлы.",
    s2t: "Сгенерировать", s2p: "Модель предлагает код по твоей спеке. Она предлагает, но не решает.",
    s3t: "Проверить результат", s3p: "Анализатор проверяет сгенерированный код. Находки обоих проходов сохраняются.",
    s4t: "Сверить", s4p: "Шесть проверок сравнивают код с обещанием: структура, синтаксис, контракт, покрытие, поведение, соответствие.",
    s5t: "Creator / исправленная версия", s5p: "Creator возвращает целые файлы с исправлениями по находкам, сохраняя исходную спеку.",
    s6t: "Проверить исправление", s6p: "Validator повторно запускает шесть проверок на исправленных Creator файлах и той же спеке.",
    s7t: "Финальная генерация", s7p: "После валидации Generator собирает итоговую полную версию и честно помечает её как непроверенную повторно.",
    correctedVersion: "Исправленная версия (проверена после Creator)", finalVersion: "Итоговая версия Generator (не проверена повторно)",
    howFoot: "Побеждает строжайший вердикт. Что не проверено, то перечислено, а не спрятано.",
    workEyebrow: "рабочий стол", workTitle: "Попробуй на своём коде",
    workLead: "Вставь код, спеку или логи ниже и нажми «запустить». Получишь вердикт, что не так и как исправить, и отчёт, который можно переслать.",
    send: "отправить", run: "запустить", hear: "🔊 прочитать", json: "↓ json",
    textPh: "напиши или нажми микрофон и говори…",
    questionPh: "\u0414\u043e\u0431\u0430\u0432\u044c\u0442\u0435 \u0432\u043e\u043f\u0440\u043e\u0441 \u0438\u043b\u0438 \u043f\u043e\u0436\u0435\u043b\u0430\u043d\u0438\u0435",
    materialPh: "например, вставь что-то такое:\n\n@app.get(\"/user\")\ndef user():\n    name = request.args.get(\"name\", \"\")\n    cur.execute(f\"select * from users where name = '{name}'\")",
    exampleQuestion: "это безопасно?",
    sampleBtn: "\u0417\u0430\u043f\u043e\u043b\u043d\u0438\u0442\u044c \u043f\u0440\u0438\u043c\u0435\u0440",
    keySys: "У хаба нет ключа модели. Правила проверяют код бесплатно; чтобы код читала ещё и модель, добавь ключ ниже: Anthropic, DeepSeek или ChatGPT (для Ollama ключ не нужен; ключ остаётся в этом браузере).",
    chooseProject: "выбрать папку проекта",
    chooseFile: "Выбрать файл с исходным кодом",
    fileNote: "файл читается в браузере и передаётся вместе с запуском",
    runEyebrow: "\u0417\u0430\u0449\u0438\u0442\u0430 \u043a\u043e\u0434\u0430 \u0438 \u043f\u043e\u043b\u043d\u044b\u0439 \u0446\u0438\u043a\u043b",
    runTitle: "\u0417\u0430\u043f\u0443\u0441\u0442\u0438\u0442\u044c \u043f\u043e\u043b\u043d\u0443\u044e \u0446\u0435\u043f\u043e\u0447\u043a\u0443",
    runIntro: "Выбери режим, добавь код и требования, затем просмотри отчёт и итоговую проверку исправленной версии.",
    modeLabel: "\u0420\u0435\u0436\u0438\u043c \u0440\u0430\u0431\u043e\u0442\u044b",
    modeFull: "Полный цикл",
    modeGenerate: "\u0413\u0435\u043d\u0435\u0440\u0430\u0446\u0438\u044f + \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0430",
    modeAnalyse: "\u0422\u043e\u043b\u044c\u043a\u043e \u0430\u043d\u0430\u043b\u0438\u0437",
    materialLabel: "\u0418\u0441\u0445\u043e\u0434\u043d\u044b\u0439 \u043a\u043e\u0434 \u0438\u043b\u0438 \u0444\u0430\u0439\u043b\u044b",
    specLabel: "\u0427\u0442\u043e \u0434\u043e\u043b\u0436\u0435\u043d \u0434\u0435\u043b\u0430\u0442\u044c \u043a\u043e\u0434?",
    specPh: "\u041e\u043f\u0438\u0448\u0438\u0442\u0435 \u043e\u0436\u0438\u0434\u0430\u0435\u043c\u043e\u0435 \u043f\u043e\u0432\u0435\u0434\u0435\u043d\u0438\u0435 \u0438 \u043e\u0433\u0440\u0430\u043d\u0438\u0447\u0435\u043d\u0438\u044f.",
    questionLabel: "\u0414\u043e\u043f\u043e\u043b\u043d\u0438\u0442\u0435\u043b\u044c\u043d\u044b\u0435 \u0443\u043a\u0430\u0437\u0430\u043d\u0438\u044f \u0434\u043b\u044f \u043c\u043e\u0434\u0435\u043b\u0438",
    fullFlowHint: "Для всех семи этапов и проверенной исправленной версии добавь исходный код и спецификацию. Только спецификация запускает генерацию и проверку.",
    stageInput: "проверка входа", stageGenerate: "генерация", stageOutput: "проверка результата",
    stageValidate: "валидация", stageCreator: "Creator", stageFinalValidate: "проверка исправления", stageFinalGenerate: "финальная генерация",
    modelTitle: "\u041f\u043e\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u0435 \u043c\u043e\u0434\u0435\u043b\u0438",
    modelHint: "\u0414\u043b\u044f \u0433\u0435\u043d\u0435\u0440\u0430\u0446\u0438\u0438 \u0438 Creator \u043d\u0443\u0436\u043d\u0430 \u043c\u043e\u0434\u0435\u043b\u044c. API-\u043a\u043b\u044e\u0447 \u0445\u0440\u0430\u043d\u0438\u0442\u0441\u044f \u0432 \u044d\u0442\u043e\u043c \u0431\u0440\u0430\u0443\u0437\u0435\u0440\u0435 \u0438 \u043f\u0435\u0440\u0435\u0434\u0430\u0451\u0442\u0441\u044f \u0441 \u0437\u0430\u043f\u0443\u0441\u043a\u043e\u043c. Ollama \u0440\u0430\u0431\u043e\u0442\u0430\u0435\u0442 \u0431\u0435\u0437 \u043a\u043b\u044e\u0447\u0430.",
    providerLabel: "\u041f\u0440\u043e\u0432\u0430\u0439\u0434\u0435\u0440",
    modelNameLabel: "\u041c\u043e\u0434\u0435\u043b\u044c (\u043d\u0435\u043e\u0431\u044f\u0437\u0430\u0442\u0435\u043b\u044c\u043d\u043e)",
    modelNamePh: "\u041d\u0430\u0437\u0432\u0430\u043d\u0438\u0435 \u043c\u043e\u0434\u0435\u043b\u0438",
    apiKeyLabel: "API-\u043a\u043b\u044e\u0447",
    apiKeyPh: "\u0412\u0441\u0442\u0430\u0432\u044c\u0442\u0435 \u043a\u043b\u044e\u0447 \u043f\u0440\u043e\u0432\u0430\u0439\u0434\u0435\u0440\u0430",
    save: "\u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c \u043a\u043b\u044e\u0447",
    clear: "\u0423\u0434\u0430\u043b\u0438\u0442\u044c \u043a\u043b\u044e\u0447",
    projectEmpty: "\u0424\u0430\u0439\u043b\u044b \u043f\u0440\u043e\u0435\u043a\u0442\u0430 \u0435\u0449\u0451 \u043d\u0435 \u0434\u043e\u0431\u0430\u0432\u043b\u0435\u043d\u044b.",
    projectHint: "Папка проверяется только статическими правилами Vishap. Файлы передаются сервису VishapHub, но не отправляются провайдеру модели. До 200 текстовых файлов / 500 000 символов; сборки, бинарные файлы и очевидные файлы или значения ключей пропускаются.",
    projectLoaded: "файлов: {files} · символов: {chars}{skipped}",
    projectSkipped: " · пропущено сборок, бинарных файлов и файлов/значений с ключами: {n}",
    projectNoText: "Не найдено читаемых текстовых файлов.",
    projectTooMany: "Выбери не больше 200 текстовых файлов. Предыдущий выбор очищен.",
    projectTooLarge: "В выбранных файлах больше 500 000 символов. Предыдущий выбор очищен.",
    projectReadError: "Не удалось прочитать один из файлов как текст. Предыдущий выбор очищен.",
    projectQuestionBlocked: "Папка проверяется только правилами, файлы не отправляются модели. Очисти выбранные файлы, чтобы спросить модель о вставленном коде.",
    projectInputConflict: "\u0414\u043b\u044f \u0430\u043d\u0430\u043b\u0438\u0437\u0430 \u043f\u0430\u043f\u043a\u0438 \u043e\u0447\u0438\u0441\u0442\u0438\u0442\u0435 \u043f\u043e\u043b\u044f \u043a\u043e\u0434\u0430, \u0442\u0440\u0435\u0431\u043e\u0432\u0430\u043d\u0438\u0439 \u0438 \u0438\u043d\u0441\u0442\u0440\u0443\u043a\u0446\u0438\u0439.",
    projectDuplicate: "У двух файлов совпадает относительный путь: {path}. Выбери одну папку проекта.",
    fullNeedsCodeSpec: "\u0414\u043b\u044f \u043f\u043e\u043b\u043d\u043e\u0433\u043e \u0446\u0438\u043a\u043b\u0430 \u043d\u0443\u0436\u043d\u044b \u0438 \u0438\u0441\u0445\u043e\u0434\u043d\u044b\u0439 \u043a\u043e\u0434, \u0438 \u0442\u0440\u0435\u0431\u043e\u0432\u0430\u043d\u0438\u044f.",
    specRequired: "\u0414\u043e\u0431\u0430\u0432\u044c\u0442\u0435 \u0442\u0440\u0435\u0431\u043e\u0432\u0430\u043d\u0438\u044f \u0434\u043b\u044f \u0433\u0435\u043d\u0435\u0440\u0430\u0446\u0438\u0438.",
    analyseNeedsCode: "\u0414\u043e\u0431\u0430\u0432\u044c\u0442\u0435 \u043a\u043e\u0434 \u0438\u043b\u0438 \u0432\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u043f\u0430\u043f\u043a\u0443 \u043f\u0440\u043e\u0435\u043a\u0442\u0430.",
    analyseStaticOnly: "\u0420\u0435\u0436\u0438\u043c \u0430\u043d\u0430\u043b\u0438\u0437\u0430 \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0435\u0442 \u0442\u043e\u043b\u044c\u043a\u043e \u0441\u0442\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438\u0435 \u043f\u0440\u0430\u0432\u0438\u043b\u0430. \u041e\u0447\u0438\u0441\u0442\u0438\u0442\u0435 \u043f\u043e\u043b\u044f \u0442\u0440\u0435\u0431\u043e\u0432\u0430\u043d\u0438\u0439 \u0438 \u0438\u043d\u0441\u0442\u0440\u0443\u043a\u0446\u0438\u0439 \u0438\u043b\u0438 \u0432\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0440\u0435\u0436\u0438\u043c \u0433\u0435\u043d\u0435\u0440\u0430\u0446\u0438\u0438.",
    keyHint: "Необязательно. Без ключа работают только правила; с твоим ключом и вопросом код читает ещё и модель, а побеждает более строгий вердикт. Ключ хранится в этом браузере и передаётся вместе с запуском.",
    noModelSummary: "\u042d\u0442\u0443 \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0443 \u043d\u0435 \u0447\u0438\u0442\u0430\u043b\u0430 \u043c\u043e\u0434\u0435\u043b\u044c, \u043f\u043e\u044d\u0442\u043e\u043c\u0443 \u0441\u0432\u043e\u0434\u043a\u0438 \u043c\u043e\u0434\u0435\u043b\u0438 \u043d\u0435\u0442. \u041f\u0440\u0430\u0432\u0438\u043b\u0430 \u043d\u0430\u0448\u043b\u0438 \u043d\u0430\u0445\u043e\u0434\u043e\u043a: {n}. \u041e\u0442\u043a\u0440\u043e\u0439 \u0432\u043a\u043b\u0430\u0434\u043a\u0443 findings. \u0414\u043e\u0431\u0430\u0432\u044c \u0441\u0432\u043e\u0439 \u043a\u043b\u044e\u0447 \u043d\u0438\u0436\u0435, \u0447\u0442\u043e\u0431\u044b \u043a\u043e\u0434 \u043f\u0440\u043e\u0447\u0438\u0442\u0430\u043b\u0430 \u0435\u0449\u0451 \u0438 \u043c\u043e\u0434\u0435\u043b\u044c.",
    verdictHint: "REQUIRES_REVIEW значит: человеку стоит прочитать находки. SAFE по одним правилам пока доступен только для Java после полной проверки без находок; остальные языки требуют просмотра.",
    working: "работаю…", nothing: "нечего проверять", refused: "отказ",
    verdictLabel: "вердикт", notChecked: "не проверено", openReport: "открыть отчёт",
    statRisk: "вердикт риска", statFix: "исправление", statVerify: "проверка",
    reportAt: "прогон", copy: "копировать", copied: "скопировано", noAccess: "нет доступа",
    micOff: "в этом браузере нет распознавания речи; есть в Chrome и Edge",
    micNo: "микрофон недоступен или отклонён",
    savedKey: "ключ сохранён в этом браузере", clearedKey: "ключ стёрт",
    streamLost: "поток закончился без вердикта",
    truncated: "…ответ обрезан лимитом токенов; если важно — попроси продолжить",
    modeHint: "\u041f\u043e\u043b\u043d\u0430\u044f \u0446\u0435\u043f\u043e\u0447\u043a\u0430 \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0435\u0442 \u043a\u043e\u0434 \u0438 \u0442\u0440\u0435\u0431\u043e\u0432\u0430\u043d\u0438\u044f. \u0420\u0435\u0436\u0438\u043c \u00ab\u0422\u043e\u043b\u044c\u043a\u043e \u0430\u043d\u0430\u043b\u0438\u0437\u00bb \u043f\u0440\u043e\u0432\u0435\u0440\u044f\u0435\u0442 \u043a\u043e\u0434 \u0441\u0442\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438\u043c\u0438 \u043f\u0440\u0430\u0432\u0438\u043b\u0430\u043c\u0438.",
    keyRequired: "\u0414\u043e\u0431\u0430\u0432\u044c\u0442\u0435 API-\u043a\u043b\u044e\u0447 \u0434\u043b\u044f \u0432\u044b\u0431\u0440\u0430\u043d\u043d\u043e\u0433\u043e \u043f\u0440\u043e\u0432\u0430\u0439\u0434\u0435\u0440\u0430 \u0438\u043b\u0438 \u0432\u044b\u0431\u0435\u0440\u0438\u0442\u0435 Ollama.",
    creatorRescan: "Повторно проверить файлы Creator статическими правилами",
    creatorRescanBusy: "Проверяю точные файлы Creator…",
    creatorRescanHint: "Проверка использует только статические правила Vishap. Тесты и поведение программы не проверяются.",
    creatorRescanDone: "Статическая проверка завершена: находок — {n}. Тесты и поведение программы не проверялись.",
    creatorRescanFailed: "Не удалось выполнить статическую проверку: {error}",
    creatorRescanReport: "Открыть отчёт статической проверки",
    paletteLabel: "Цветовая палитра",
    paletteBalanced: "Средний режим",
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
  document.querySelectorAll("[data-i18n-aria]").forEach(el => { el.setAttribute("aria-label", t(el.dataset.i18nAria)); });
  const btn = document.getElementById("lang");
  if (btn) btn.textContent = lang === "ru" ? "EN" : "RU";
}

const $ = (id) => document.getElementById(id);
const chat = $("chat");
const voiceOn = {v:false};
const history = [];

function bubble(role, text){
  if (!chat) return null;
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
function loadExample(){
  clearProjectFiles();
  $("mode").value = "generate+validate+analyse";
  $("material").value = "cur.execute(\"select * from users where name = '\" + name + \"'\")";
  $("spec").value = "Add a function that safely looks up a user by name. Use parameterized SQL, validate the input, and return a clear not-found result.";
  $("question").value = "";
  $("mode-hint").textContent = t("modeHint");
  $("material").focus();
  $("run-title").scrollIntoView({behavior:"smooth", block:"start"});
}
$("mode").onchange = () => { $("mode-hint").textContent = t("modeHint"); };
if ($("tryExample")) $("tryExample").onclick = loadExample;
if ($("sampleRun")) $("sampleRun").onclick = loadExample;

const providerValue = () => { const v = $("provider").value; return ["deepseek","openai","ollama"].includes(v) ? v : "anthropic"; };
const modelValue = () => ($("modelname").value || "").trim();
try { $("provider").value = localStorage.getItem("vishap_provider") || "anthropic"; } catch (e) {}
try { $("modelname").value = localStorage.getItem("vishap_model") || ""; } catch (e) {}
$("provider").onchange = () => { try { localStorage.setItem("vishap_provider", providerValue()); } catch (e) {} };
$("modelname").onchange = () => { try { localStorage.setItem("vishap_model", modelValue()); } catch (e) {} };
$("save").onclick = () => { localStorage.setItem("vishap_key", $("key").value.trim()); localStorage.setItem("vishap_provider", providerValue()); bubble("sys", t("savedKey")); };
$("clear").onclick = () => { localStorage.removeItem("vishap_key"); $("key").value=""; bubble("sys", t("clearedKey")); };
$("key").value = localStorage.getItem("vishap_key") || "";

async function ask(message){
  if (!message.trim()) return;
  bubble("user", message);
  history.push({role:"user", content:message});
  const thinking = bubble("sys", "…");
  try {
    const res = await fetch("/chat", {method:"POST", headers:{"content-type":"application/json"},
      body: JSON.stringify({message, messages: history, api_key: localStorage.getItem("vishap_key") || "", provider: providerValue(), model: modelValue()})});
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

if ($("send") && $("text")) {
  $("send").onclick = () => { const line = $("text").value; $("text").value=""; ask(line); };
  $("text").addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey){ e.preventDefault(); $("send").click(); } });
  document.querySelectorAll(".chip").forEach(c => c.onclick = () => ask(c.dataset.q));
}

function clearProjectFiles(){
  projectFiles = Object.create(null);
  projectStatus = {type:"empty"};
  if ($("picker")) $("picker").value = "";
  if ($("folderPicker")) $("folderPicker").value = "";
  if (previousMode){ $("mode").value = previousMode; previousMode = ""; }
  $("mode").disabled = false;
  $("model-key").hidden = false;
  updateProjectSummary();
}

function updateProjectSummary(){
  const summary = $("projectSummary");
  if (!summary) return;
  const names = Object.keys(projectFiles);
  if (!names.length){
    summary.textContent = projectStatus.type === "error"
      ? t(projectStatus.key).replace("{path}", projectStatus.path || "")
      : t("projectEmpty");
    return;
  }
  const chars = Object.values(projectFiles).reduce((sum, value) => sum + value.length, 0);
  const skippedText = projectStatus.skipped ? t("projectSkipped").replace("{n}", String(projectStatus.skipped)) : "";
  summary.textContent = t("projectLoaded").replace("{files}", String(names.length))
    .replace("{chars}", chars.toLocaleString(lang === "ru" ? "ru-RU" : "en-US"))
    .replace("{skipped}", skippedText);
}

function projectError(key, path = ""){
  projectStatus = {type:"error", key, path};
  updateProjectSummary();
}

async function loadProjectFiles(fileList){
  clearProjectFiles();
  const skipDirs = new Set([".git", ".ssh", ".aws", ".azure", "credentials", "secrets", "node_modules", ".venv", "venv", "vendor", "dist", "build", "coverage", "__pycache__", ".next", "target"]);
  const binaryExt = /\.(7z|avif|bmp|class|dll|dylib|exe|gif|gz|ico|jpeg|jpg|lockb|mp3|mp4|otf|pdf|png|pyc|so|svgz|tar|ttf|wasm|webp|woff2?|zip)$/i;
  const credentialFile = /(^\.env($|\.)|^id_(rsa|ed25519)$|credential|secret|\.(pem|key|p12|pfx|jks)$)/i;
  const credentialContent = /(?:api[_-]?key|access[_-]?key|secret|password|token|private[_-]?key)\s*[:=]\s*["'`][^"'`\r\n]{8,}["'`]|\b(?:sk-[A-Za-z0-9_-]{16,}|AKIA[A-Z0-9]{16}|gh[pousr]_[A-Za-z0-9]{20,})\b/i;
  const candidates = [];
  let skipped = 0;
  for (const file of Array.from(fileList || [])){
    const path = (file.webkitRelativePath || file.name).replace(/\\/g, "/");
    const name = path.split("/").pop();
    if (path.split("/").some(part => skipDirs.has(part.toLowerCase())) || binaryExt.test(path) || credentialFile.test(name)) { skipped++; continue; }
    candidates.push({file, path});
  }
  if (candidates.length > 200){ projectError("projectTooMany"); return; }
  const loaded = Object.create(null);
  let chars = 0;
  let bytes = 0;
  try {
    for (const {file, path} of candidates){
      if (Object.prototype.hasOwnProperty.call(loaded, path)){ projectError("projectDuplicate", path); return; }
      bytes += file.size;
      if (bytes > 2_000_000){ projectError("projectTooLarge"); return; }
      const text = await file.text();
      if (text.includes("\0")){ skipped++; continue; }
      if (credentialContent.test(text)){ skipped++; continue; }
      if (chars + text.length > 500_000){ projectError("projectTooLarge"); return; }
      loaded[path] = text;
      chars += text.length;
    }
  } catch (e) { projectError("projectReadError"); return; }
  if (!Object.keys(loaded).length){ projectError("projectNoText"); return; }
  projectFiles = loaded;
  previousMode = $("mode").value;
  $("mode").value = "analyse";
  $("mode").disabled = true;
  $("model-key").hidden = true;
  projectStatus = {type:"loaded", skipped};
  updateProjectSummary();
}

$("drop").onclick = () => $("picker").click();
$("chooseProject").onclick = () => $("folderPicker").click();
$("drop").addEventListener("keydown", e => {
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("picker").click(); }
});
$("picker").onchange = async e => {
  const file = e.target.files && e.target.files[0];
  if (file){
    clearProjectFiles();
    try { $("material").value = await file.text(); }
    catch (err) { $("verdict").textContent = t("projectReadError"); }
  }
  e.target.value = "";
};
$("folderPicker").onchange = async e => {
  if (e.target.files && e.target.files.length) await loadProjectFiles(e.target.files);
  e.target.value = "";
};
["dragenter","dragover"].forEach(ev => $("drop").addEventListener(ev, e => { e.preventDefault(); $("drop").classList.add("hot"); }));
["dragleave","drop"].forEach(ev => $("drop").addEventListener(ev, e => { e.preventDefault(); $("drop").classList.remove("hot"); }));
$("drop").addEventListener("drop", async e => {
  const file = e.dataTransfer.files && e.dataTransfer.files[0];
  if (file){
    clearProjectFiles();
    try { $("material").value = await file.text(); }
    catch (err) { $("verdict").textContent = t("projectReadError"); }
  }
});

const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
const micOn = (state) => {
  if (!$("mic")) return;
  $("mic").classList.toggle("on", state);
  $("mic").setAttribute("aria-pressed", String(state));
};
if ($("mic")) $("mic").onclick = () => {
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
let projectFiles = Object.create(null);
let projectStatus = {type:"empty"};
let previousMode = "";
try { const saved = sessionStorage.getItem("vishap_last"); if (saved) { lastResult = JSON.parse(saved); $("download").disabled = false; } } catch (e) {}

const sevRank = {critical: 4, high: 3, medium: 2, low: 1};
const readers = f => new Set(f.seen_by || []).size;

// More than one reader first, then the rest; by severity within each, in the order found within a tie.
// Nothing is dropped: only the order of the list changes.
function byAgreement(list){
  const rank = f => sevRank[String(f.severity || "").toLowerCase()] || 0;
  return list.map((f, i) => [f, i])
    .sort((a, b) => (readers(b[0]) > 1) - (readers(a[0]) > 1) || rank(b[0]) - rank(a[0]) || a[1] - b[1])
    .map(x => x[0]);
}

function groupFindings(list, fn){
  const own = byAgreement(list.filter(f => !f.in_patch)), pat = list.filter(f => f.in_patch);
  const both = own.some(f => readers(f) > 1) && own.some(f => readers(f) <= 1);
  const shown = [];
  let last = null;
  own.forEach(f => {
    const kind = readers(f) > 1 ? "many" : "one";
    if (both && kind !== last) shown.push(kind === "many" ? "SEEN BY MORE THAN ONE READER" : "SEEN BY ONE READER");
    last = kind;
    shown.push(fn(f));
  });
  return [...shown, ...(pat.length ? ["IN THE MODEL'S PATCH (line numbers refer to the patch)"] : []), ...pat.map(fn)];
}

function renderReport(data){
  lastResult = data;
  try { sessionStorage.setItem("vishap_last", JSON.stringify(data)); } catch (e) {}
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
        const by = (f.seen_by || []).length > 1 ? f.seen_by.join(" + ") : (f.source || "");
        return `${(f.severity||"").toUpperCase()}${f.rule ? " \u00b7 " + f.rule : ""}${f.line ? " @ " + f.line : ""}${by ? " [" + by + "]" : ""}\n  ${f.message||""}${f.fix ? "\n  fix: " + f.fix : ""}${f.possibly_covered_by ? "\n  possibly covered by " + f.possibly_covered_by : ""}`;
      }).join("\n\n")
      : "nothing matched",
    patch: Object.keys(data.patch || {}).length
      ? Object.entries(data.patch).map(([n, c]) => `── ${n} ──\n${c}`).join("\n\n")
      : "no patch proposed",
    [t("correctedVersion")]: Object.keys(data.corrected_version || {}).length
      ? Object.entries(data.corrected_version).map(([n, c]) => `── ${n} ──\n${c}`).join("\n\n")
      : "no corrected version produced",
    [t("finalVersion")]: Object.keys(data.final_version || {}).length
      ? Object.entries(data.final_version).map(([n, c]) => `── ${n} ──\n${c}`).join("\n\n")
      : "no final generator version produced",
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
  const st = data.statuses || {};
  const chip = (label, value) => value ? `<span class="stat"><span class="stat-k">${escapeHtml(label)}</span> <b>${escapeHtml(value)}</b></span>` : "";
  const statusLine = st.risk
    ? `<div class="stat-row">${chip(t("statRisk"), st.risk.verdict)}${chip(t("statFix"), (st.fix || {}).status)}${chip(t("statVerify"), (st.verification || {}).status)}</div>`
    : "";
  box.innerHTML = statusLine + `<div class="tabs">` + names.map((n, i) =>
      `<span class="tab ${i===0?"on":""}" data-pane="${escapeHtml(n)}">${escapeHtml(n)}</span>`).join("")
    + `<span class="copy" id="copy">${escapeHtml(t("copy"))}</span></div>
    <div class="pane" id="pane"></div>
    <div class="report-meta">
      ${fp.id ? `<span>${escapeHtml(t("reportAt"))} <code>${escapeHtml(fp.id)}</code></span>` : ""}
      ${reportLink}
    </div>
    ${Object.keys(data.corrected_version || {}).length
      ? `<div class="creator-rescan"><p class="hint">${escapeHtml(t("creatorRescanHint"))}</p><button type="button" class="btn ghost sm" id="creatorRescan">${escapeHtml(t("creatorRescan"))}</button><div id="creatorRescanResult" class="creator-rescan-result" aria-live="polite"></div></div>`
      : ""}
    <div id="qs"></div>`;

  const rescan = $("creatorRescan");
  if (rescan){
    const correctedFiles = data.corrected_version;
    rescan.onclick = async () => {
      rescan.disabled = true;
      const resultBox = $("creatorRescanResult");
      resultBox.textContent = t("creatorRescanBusy");
      try {
        const body = JSON.stringify({files: correctedFiles, intent: "analyse"});
        if (new TextEncoder().encode(body).byteLength > 3_800_000) throw new Error(t("projectTooLarge"));
        const response = await fetch("/run", {method:"POST", headers:{"Content-Type":"application/json"}, body});
        const scan = await response.json();
        if (!response.ok || !scan.ok) throw new Error(scan.error || `HTTP ${response.status}`);
        const count = (scan.findings || []).length;
        const report = scan.fingerprint && scan.fingerprint.id
          ? `<a href="/r/${encodeURIComponent(scan.fingerprint.id)}" target="_blank" rel="noopener">${escapeHtml(t("creatorRescanReport"))} ↗</a>`
          : "";
        resultBox.textContent = t("creatorRescanDone").replace("{n}", String(count));
        if (report) resultBox.insertAdjacentHTML("beforeend", " · " + report);
      } catch (err) {
        resultBox.textContent = t("creatorRescanFailed").replace("{error}", err && err.message ? err.message : "request failed");
      } finally {
        rescan.disabled = false;
      }
    };
  }

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
  const stages = [
    ["analyser_input", t("stageInput")], ["generator", t("stageGenerate")],
    ["analyser", t("stageOutput")], ["validator", t("stageValidate")],
    ["creator", t("stageCreator")], ["creator_validator", t("stageFinalValidate")],
    ["final_generator", t("stageFinalGenerate")],
  ];
  $("progress").innerHTML = stages.map(([key, label]) =>
    `<span class="step ${states[key]||""}"><span class="b"></span>${escapeHtml(label)}</span>`).join("");
}

function showResult(data, started){
  if (!data.ok){
    const states = {};
    let seenAnalyser = 0;
    for (const step of data.steps || []){
      let key = step.stage;
      if (step.stage === "analyser") key = ++seenAnalyser === 1 ? "analyser_input" : "analyser";
      if (step.stage === "validator" && /after Creator/i.test(step.detail || "")) key = "creator_validator";
      states[key] = step.ok ? "done" : "fail";
    }
    setProgress(states);
    $("verdict").innerHTML = `<b>${escapeHtml(t("refused"))}</b> ${escapeHtml(data.error || "failed")}`;
    if (data.fingerprint && data.fingerprint.id) renderReport(data);
    return;
  }

  const checks = data.checks || {};
  const checkState = check => !check ? "" : (check.status === "NOT_RUN" || /FAIL|ERROR/i.test(check.verdict || "") ? "fail" : "done");
  const states = {"model": checks.generator ? "done" : ""};
  Object.assign(states, {
    analyser_input: checkState(checks.analyser_input),
    generator: checkState(checks.generator),
    analyser: checkState(checks.analyser),
    validator: checkState(checks.validator),
    creator: checkState(checks.creator),
    creator_validator: checkState(checks.creator_validator),
    final_generator: checkState(checks.final_generator),
  });
  states.verdict = /SAFE|PASS/i.test(data.verdict) ? "done" : "fail";
  setProgress(states);

  const bits = [];
  if (checks.generator) bits.push(`generator <b>${escapeHtml(checks.generator.verdict)}</b>`);
  if (checks.analyser) bits.push(`analyser <b>${escapeHtml(checks.analyser.verdict)}</b>`);
  if (checks.validator) bits.push(`validator <b>${escapeHtml(checks.validator.verdict)}</b>`);
  if (checks.creator_validator) bits.push(`validator after Creator <b>${escapeHtml(checks.creator_validator.verdict || checks.creator_validator.status)}</b>`);
  if (checks.final_generator) bits.push(`final generator <b>${escapeHtml(checks.final_generator.files || 0)} file(s)</b>`);
  const secs = ((performance.now() - started) / 1000).toFixed(1);
  $("verdict").innerHTML = `${escapeHtml(t("verdictLabel"))} <b>${escapeHtml(data.verdict)}</b>`
    + (bits.length ? " · " + bits.join(" · ") : "")
    + ` <span class="dim">· ${secs}s</span>`;

  $("verdict").dataset.v = data.verdict || "";
  renderReport(data);
  const doneCount = [checks.analyser_input, checks.generator, checks.analyser, checks.validator, checks.creator, checks.creator_validator, checks.final_generator].filter(Boolean).length;
  if ($("cardVerdict")) {
    $("cardVerdict").textContent = data.verdict || "—";
    $("cardVerdict").dataset.v = data.verdict || "";
    $("cardChecks").textContent = `${doneCount} of 7`;
    $("cardFindings").textContent = String((data.findings || []).length);
    $("cardTag").textContent = "live";
  }
  $("hear").disabled = false;
  $("download").disabled = false;

  lastSpoken = `${data.summary || ""} ${t("verdictLabel")}: ${data.verdict}.`;
  if (voiceOn.v) sayText(lastSpoken);
}

async function pipeline(){
  const material = $("material").value;
  const question = $("question").value;
  // The magic surface has one input; use it as both context and specification
  // so the seven-stage backend remains intact without exposing its machinery.
  const spec = $("spec").value || (material.trim() ? material : "");
  const intent = $("mode").value;
  const hasProjectFiles = Object.keys(projectFiles).length > 0;
  if (hasProjectFiles && question.trim()){
    $("verdict").textContent = t("projectQuestionBlocked");
    return;
  }
  if (hasProjectFiles && (material.trim() || spec.trim() || question.trim())){
    $("verdict").textContent = t("projectInputConflict"); return;
  }
  if (hasProjectFiles && intent !== "analyse"){
    $("verdict").textContent = t("analyseStaticOnly"); return;
  }
  if (!hasProjectFiles && intent === "generate+validate+analyse" && (!material.trim() || !spec.trim())){
    $("verdict").textContent = t("fullNeedsCodeSpec"); return;
  }
  if (!hasProjectFiles && intent === "generate+validate" && !spec.trim()){
    $("verdict").textContent = t("specRequired"); return;
  }
  if (!hasProjectFiles && intent === "analyse" && (!material.trim() || spec.trim() || question.trim())){
    $("verdict").textContent = material.trim() ? t("analyseStaticOnly") : t("analyseNeedsCode"); return;
  }
  if (!hasProjectFiles && intent !== "analyse" && providerValue() !== "ollama" && !localStorage.getItem("vishap_key")){
    $("verdict").textContent = t("keyRequired"); $("key").focus(); return;
  }
  if (!material.trim() && !spec.trim() && !question.trim() && !hasProjectFiles){ $("verdict").innerHTML = `<b>${escapeHtml(t("nothing"))}</b>`; return; }

  const started = performance.now();
  $("verdict").dataset.v = ""; $("verdict").textContent = t("working");
  $("report").innerHTML = "";
  $("hear").disabled = true;
  $("download").disabled = true;
  setProgress({"analyser_input":"run"});

  const payload = hasProjectFiles
    ? {files: projectFiles, intent: "analyse"}
    : {material, question, spec, intent,
       api_key: intent === "analyse" ? "" : (localStorage.getItem("vishap_key") || ""),
       provider: providerValue(),
       model: intent === "analyse" ? "" : modelValue()};
  const body = JSON.stringify(payload);
  if (hasProjectFiles && new TextEncoder().encode(body).byteLength > 3_800_000){
    $("verdict").textContent = t("projectTooLarge");
    return;
  }
  const wake = setTimeout(() => { $("waking").style.display = "block"; }, 8000);
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
    const liveStates = {};
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
          if (data.stage === "generator") liveStates.generator = "done";
          if (data.stage === "analyser") liveStates[data.target === "input" ? "analyser_input" : "analyser"] = "done";
          if (data.stage === "validator") liveStates[data.target === "creator" ? "creator_validator" : "validator"] = data.verdict === "NOT_RUN" ? "fail" : "done";
          if (data.stage === "creator") liveStates.creator = "done";
          if (data.stage === "final_generator") liveStates.final_generator = "done";
          setProgress(liveStates);
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
updateProjectSummary();
$("lang").onclick = () => {
  lang = lang === "ru" ? "en" : "ru";
  localStorage.setItem("vishap_lang", lang);
  applyLang();
  updateProjectSummary();
};
fetch("/health").then(r=>r.json()).then(d=>{$("ver").textContent = d.version;}).catch(()=>{});
