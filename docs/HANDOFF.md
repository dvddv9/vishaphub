# HANDOFF: Vishap v7.3.16

**Дата:** 2026-10-24
**От:** senior-разработчик
**Кому:** следующий senior-разработчик

## 📊 Состояние

- **Версия:** v7.3.16
- **HEAD:** fca8d4f (v7.3.17 — chore: tauri.conf -> 7.3.16)
- **Тесты:** 674 passed, 8 skipped (pytest)
- **GitHub:** main + tag v7.3.17
- **PyPI:** vishap-analyzer==7.3.16
- **Tauri Desktop:** v7.3.16 (NSIS + MSI installer)

## 🚀 Что нового (v7.3.11 — v7.3.16)

| Версия | Что |
|---|---|
| **v7.3.11** | Self-adversarial red team (VISHAP_REDTEAM=1) + runbook в Transmitter. |
| **v7.3.12** | DeepSeek API как default (api.deepseek.com/v1), DSH — optional. |
| **v7.3.13** | Cross-language translator (VISHAP_TRANSLATOR=1). |
| **v7.3.14** | Test-first loop (VISHAP_TESTER=1) + sandbox.py. |
| **v7.3.15** | Fix-loop (VISHAP_FIXER=1) + apply_fix_and_verify. |
| **v7.3.16** | 5 LLM providers в UI (custom / openai / groq / ollama / dsh), светлая тема, dir() -> locals() fix. |

## 🏗️ Архитектура (v7.3.16)

- **Backend:** Python 3.12, FastAPI, Uvicorn (порт 5001)
- **Desktop:** Tauri 2 (Rust) + Next.js 16 (frontend)
- **LLM:** custom (OpenAI-compatible) — default DeepSeek API at v7.3.16; since v7.4.7 the deployment default is Claude (api.anthropic.com)
- **Pipeline:** 6-stage (stage0 → stage5) + 4 optional loops
- **Data:** VISHAP_DATA_DIR (по умолчанию C:\AI\conveyor_app\data)

### Optional loops (флаги .env)

- VISHAP_REDTEAM=1 — red team (stage2_5)
- VISHAP_TRANSLATOR=1 — translator (stage1_5)
- VISHAP_TESTER=1 — tester (stage3_5)
- VISHAP_FIXER=1 — fixer (stage4_5)

## 📦 Сборка Tauri (Windows)

cd C:\AI\conveyor_app

# 1) frontend
cd ui-next
npm install
npm run build:desktop

# 2) Tauri (Rust)
cd ..
tauri build

**Результат:**
- .exe: src-tauri/target/release/vishap-desktop.exe
- installer NSIS: bundle/nsis/Vishap_7.3.16_x64-setup.exe
- installer MSI: bundle/msi/Vishap_7.3.16_x64_en-US.msi

⚠️ **Важно:** tauri.conf.json **должен** быть без BOM (иначе expected value at line 1 column 1).
Проверка: [System.IO.File]::ReadAllBytes("...")[0..2] -> 7B 0D 0A (не EF BB BF).

## 🚀 Запуск (dev)

cd C:\AI\conveyor_app
.\.venv\Scripts\python.exe -m uvicorn src.main:app --host 127.0.0.1 --port 5001

Потом — vishap-desktop.exe (или ярлык на рабочем столе).

## 🧪 Тесты

cd C:\AI\conveyor_app
.\.venv\Scripts\python.exe -m pytest tests/ --ignore=tests/test_e2e.py -q
# -> 674 passed, 8 skipped

## 📁 Ключевые файлы (v7.3.16)

| Файл | Что |
|---|---|
| src/version.py | __version__ = "7.3.16" |
| src/pipeline/stages.py | 4 loops: stage1_5 / 2_5 / 3_5 / 4_5 |
| src/pipeline/sandbox.py | sandbox (apply_fix_and_verify) |
| src/pipeline/orchestrator.py | pipeline + merge loops |
| src/llm/client.py | _resolve_provider() |
| src/storage/mode.py | VALID_MODES = ("custom", "dsh", "openai", "groq", "ollama") |
| ui-next/src/components/LLMSettings.tsx | dropdown (5 providers) |
| src-tauri/tauri.conf.json | Tauri config (7.3.16) |
| src-tauri/Cargo.toml | Rust (7.3.16) |

## ⚠️ Грабли (важное)

1. **BOM в tauri.conf.json** -> tauri build падает. Фикс: [System.IO.File]::WriteAllText (без BOM).
2. **.venv (с точкой)** — не venv.
3. **dir()** не видит локальные переменные -> locals().
4. **OneDrive Desktop** — реальный путь C:\Users\<user>\OneDrive\Desktop, а не C:\Users\<user>\Desktop.
5. **Порт 5001** — если занят (старый backend), taskkill /PID <pid> /F.

## 🗺️ Что дальше (v7.3.17+)

- [ ] GitHub Release v7.3.17 (Latest).
- [ ] PyPI 7.3.16 (если не загружен — twine upload dist/*).
- [ ] docs/ — удалить legacy HARNESS.md.
- [ ] docker-compose.yml — проверить HARNESS_*.
- [ ] Тест Analyze через Tauri UI (pipeline end-to-end).

## 🎯 Философия

1. Dogfood на каждой фиче.
2. Test-first.
3. Идемпотентные патчи (SKIP не ERROR).
4. Fail-open для новых фич.
5. Не копировать расхождение платформ.

---

**Удачи! 674 теста — не сломай.**
## Anthropic (Claude) provider (v7.3.17+)

- **Dropdown**: `Anthropic (Claude)` в LLM Settings
- **Base URL**: `https://api.anthropic.com/v1/`
- **Model**: `claude-sonnet-4-20250514`
- **API Key**: `sk-ant-...` (из platform.claude.com)
- **Архитектура**: `custom_client.py` читает `CUSTOM_LLM_*` из `settings.json` (runtime) поверх `.env` (defaults) — изменения в UI применяются «на лету»