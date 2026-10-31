"""The first screen must tell the truth about the key and give a newcomer a way in."""
import pathlib
import re

WEB = pathlib.Path(__file__).resolve().parent.parent / "src" / "hub" / "web"


def _page() -> str:
    return (WEB / "index.html").read_text(encoding="utf-8")


def _app() -> str:
    return (WEB / "app.js").read_text(encoding="utf-8")


def test_the_page_does_not_promise_a_key_the_hub_does_not_hold():
    page = _page()
    assert "own key" not in page and "answers with its own" not in page
    assert 'data-i18n="keySys"' in page and 'data-i18n="keyHint"' in page


def test_material_comes_before_the_question_and_a_sample_runs_in_one_click():
    page = _page()
    assert page.index('id="material"') < page.index('id="question"')
    assert 'id="sampleRun"' in page and 'id="sampleRun"' in page[page.index('id="run"'):]
    assert '$("sampleRun").onclick = $("tryExample").onclick;' in _app()


def test_every_new_string_exists_in_both_languages():
    app = _app()
    for key in ("sampleBtn", "keySys", "keyHint", "verdictHint", "workLead", "questionPh", "materialPh"):
        assert len(re.findall(r"(?m)^\s*" + key + r": ", app)) == 2, key
    assert 'data-i18n="verdictHint"' in _page()


def test_a_run_nobody_read_says_so_instead_of_blaming_the_model():
    app = _app()
    assert 't("noModelSummary")' in app and "(model returned no summary)" in app
    assert 'const states = {"model": checks.generator ? "done" : ""};' in app
    assert 'const states = {"model":"done"}' not in app


def test_the_page_offers_a_provider_choice_and_sends_a_name_not_an_address():
    page = _page()
    assert 'id="provider"' in page and 'value="deepseek"' in page
    js = (pathlib.Path(__file__).parent.parent / "src" / "hub" / "web" / "app.js").read_text(encoding="utf-8")
    assert "provider: providerValue()" in js and js.count("provider: providerValue()") >= 2


def test_the_run_page_links_download_the_files():
    from hub import templates
    src = (pathlib.Path(templates.__file__)).read_text(encoding="utf-8")
    for ext in ("json", "sarif", "md"):
        assert f'.{ext}" download>' in src
