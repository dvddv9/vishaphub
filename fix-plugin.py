#!/usr/bin/env python3
"""fix-plugin.py — патч my-dsh-plugin (vishap_analyze) для v7.4.2.
Патчит src/index.ts + dist/index.js.
Запуск: python fix-plugin.py
"""
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\AI\my-dsh-plugin")  # link:C:/AI/my-dsh-plugin
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

SRC = ROOT / "src" / "index.ts"
DIST = ROOT / "dist" / "index.js"

def backup(p: Path) -> None:
    if p.exists():
        shutil.copy2(p, p.with_suffix(p.suffix + f".bak-{STAMP}"))

def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")

def write(p: Path, s: str) -> None:
    p.write_text(s, encoding="utf-8")

def patch_src() -> None:
    print(f"\n[1/2] src/index.ts")
    if not SRC.exists():
        print(f"  [!] НЕ НАЙДЕН: {SRC}")
        return
    backup(SRC)
    s = read(SRC)
    orig = s

    # 1. apiKey -> process.env
    s = s.replace(
        "const apiKey = 'test-key-12345' // CONVEYOR_API_KEY from .env",
        "const apiKey = process.env.CONVEYOR_API_KEY || 'test-key-12345' // CONVEYOR_API_KEY from .env",
    )

    # 2. fetch + signal (AbortSignal.timeout)
    s = s.replace(
        "const response = await fetch(url, {\n          method: 'POST',",
        "const response = await fetch(url, {\n          method: 'POST',\n          signal: AbortSignal.timeout(120_000),",
    )

    # 3. catch -> throw
    old_catch = '''      } catch (error: any) {
        return {
          analysis: `Error connecting to Vishap: ${error.message}. Is the backend running on port 5001?`,
          verdict: 'ERROR',
          cwe_ids: [],
        }
      }'''
    new_catch = '''      } catch (error: any) {
        throw new Error(
          `Vishap backend unavailable: ${error.message}. ` +
          `Is it running on 127.0.0.1:5001? See README.md for manual start.`,
        )
      }'''
    s = s.replace(old_catch, new_catch)

    # 4. session_id -> sha256(material)
    s = s.replace(
        "session_id: `dsh-${Date.now()}`,",
        "session_id: `dsh-${require('crypto').createHash('sha256').update(args.material).digest('hex').slice(0, 16)}`,",
    )

    # 5. render + verdict/cwe_ids
    s = s.replace(
        "render: (_args, value) => [{ type: 'text', text: value.analysis }],",
        "render: (_args, value) => [\n          { type: 'text', text: value.analysis },\n          { type: 'text', text: `\\n\\n[VERDICT] ${value.verdict} | CWE: ${value.cwe_ids.join(', ') || 'none'}` },\n        ],",
    )

    # 6. em dash (вЂ -> —)
    s = s.replace("вЂ”", "—")
    s = s.replace("РІ", "в")  # если кракозябры (отображение)
    s = s.replace("вЂ", "—")

    if s != orig:
        write(SRC, s)
        print("  [+] src/index.ts: 6 правок (apiKey, signal, throw, session_id, render, em-dash)")
    else:
        print("  [=] src/index.ts: без изменений (уже пропатчен?)")

def patch_dist() -> None:
    print(f"\n[2/2] dist/index.js")
    if not DIST.exists():
        print(f"  [!] НЕ НАЙДЕН: {DIST}")
        return
    backup(DIST)
    s = read(DIST)
    orig = s

    s = s.replace(
        "const apiKey = 'test-key-12345'; // CONVEYOR_API_KEY from .env",
        "const apiKey = process.env.CONVEYOR_API_KEY || 'test-key-12345'; // CONVEYOR_API_KEY from .env",
    )
    s = s.replace(
        "const response = await fetch(url, {\n                method: 'POST',",
        "const response = await fetch(url, {\n                method: 'POST',\n                signal: AbortSignal.timeout(120000),",
    )
    old_catch = '''        catch (error) {
            return {
                analysis: `Error connecting to Vishap: ${error.message}. Is the backend running on port 5001?`,
                verdict: 'ERROR',
                cwe_ids: [],
            };
        }'''
    new_catch = '''        catch (error) {
            throw new Error(`Vishap backend unavailable: ${error.message}. Is it running on 127.0.0.1:5001? See README.md for manual start.`);
        }'''
    s = s.replace(old_catch, new_catch)
    s = s.replace(
        "session_id: `dsh-${Date.now()}`,",
        "session_id: `dsh-${(await import('crypto')).createHash('sha256').update(args.material).digest('hex').slice(0, 16)}`,",
    )
    s = s.replace(
        "render: (_args, value) => [{ type: 'text', text: value.analysis }],",
        "render: (_args, value) => [\n                { type: 'text', text: value.analysis },\n                { type: 'text', text: `\\n\\n[VERDICT] ${value.verdict} | CWE: ${value.cwe_ids.join(', ') || 'none'}` },\n            ],",
    )

    if s != orig:
        write(DIST, s)
        print("  [+] dist/index.js: 6 правок")
    else:
        print("  [=] dist/index.js: без изменений")

def rebuild() -> None:
    print(f"\n[rebuild] npm run build")
    try:
        r = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if r.returncode == 0:
            print("  [+] build OK (dist/index.js пересобран)")
        else:
            print(f"  [!] build FAILED (rc={r.returncode})")
            print(f"  stderr: {r.stderr[:500]}")
    except FileNotFoundError:
        print("  [!] npm не найден — пропускаю build (dist/index.js пропатчен вручную)")

if __name__ == "__main__":
    print(f"=== fix-plugin.py (stamp {STAMP}) ===")
    if not ROOT.exists():
        print(f"[!] {ROOT} не существует. Проверь: link:C:/AI/my-dsh-plugin")
        sys.exit(1)
    patch_src()
    patch_dist()
    rebuild()
    print(f"\n=== DONE ===")
    print("Проверка: Get-Content $src -First 10")
