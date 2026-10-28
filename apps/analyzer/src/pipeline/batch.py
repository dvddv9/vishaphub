# -*- coding: utf-8 -*-
"""
Batch-обработка: параллельный запуск pipeline для списка материалов.

Использует ThreadPoolExecutor — для HTTP-запросов к LLM даёт полный
параллелизм (GIL отпускается во время IO).

Пример:
    from src.pipeline.batch import run_batch
    results = run_batch([
        ("def foo(): pass", "a.py"),
        ("def bar(): pass", "b.py"),
    ], max_concurrent=3)
"""
import contextvars
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.pipeline.orchestrator import run_pipeline


def run_batch(materials: list[tuple[str, str]],
              max_concurrent: int = 3,
              verbose: bool = False) -> list[dict]:
    """
    Параллельно обрабатывает список материалов.

    Args:
        materials: список (material, filename)
        max_concurrent: макс. параллельных LLM-вызовов (clamp 1..10)
        verbose: если True — печатать логи каждого pipeline

    Returns:
        Список результатов в порядке входного списка.
        При ошибке элемента — dict с {"error": ..., "filename": ...}.
    """
    if not materials:
        return []

    max_concurrent = max(1, min(int(max_concurrent), 10))

    results: list[dict | None] = [None] * len(materials)

    with ThreadPoolExecutor(max_workers=max_concurrent) as ex:
        futures = {
            ex.submit(contextvars.copy_context().run, run_pipeline, material, filename, verbose, f"-{i:02d}"): i
            for i, (material, filename) in enumerate(materials)
        }

        for future in as_completed(futures):
            i = futures[future]
            try:
                results[i] = future.result()
            except Exception as e:
                results[i] = {
                    "error": str(e),
                    "filename": materials[i][1],
                    "material_size": len(materials[i][0]),
                }

    return results  # type: ignore
