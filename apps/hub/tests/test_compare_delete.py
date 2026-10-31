"""Two runs compared, and a run deleted knowingly: what goes, what stays, who may."""
import copy
import json
import secrets
import urllib.error
import urllib.request

from test_service import ServerCase

from hub import compare, demo, server, templates
from hub.pipeline import run_plan
from hub.router import plan_for

SQLI = "cur.execute('select ' + name)\n"
CLEAN = "x = 1\n"


def record_of(material, **kw):
    data = run_plan(plan_for("analyse"), material=material, **kw).as_dict()
    return {"id": data["fingerprint"]["id"], "at": "2026-10-31T00:00:00Z", "result": data}


# the diff ---------------------------------------------------------------------------------------------

def test_the_same_run_is_identical_and_says_nothing_changed():
    a = record_of(SQLI)
    d = compare.diff(a, copy.deepcopy(a))
    assert d["identical"] and d["same_input"] and not d["verdict"]["changed"]
    assert d["findings"]["added"] == d["findings"]["removed"] == [] and d["findings"]["unchanged"] > 0
    assert "the same input" in d["summary"] and "0 finding(s) added, 0 removed" in d["summary"]


def test_different_material_is_a_different_input_and_the_findings_split_into_added_and_removed():
    d = compare.diff(record_of(SQLI), record_of(CLEAN))
    assert d["same_input"] is False and not d["identical"]
    assert d["findings"]["removed"] and d["findings"]["added"] == []
    assert any(f["rule"].startswith("sqli") for f in d["findings"]["removed"])
    assert "different input" in d["summary"]


def test_a_finding_that_only_moved_is_not_a_new_finding():
    a, b = record_of(SQLI), record_of("\n\n\n" + SQLI)               # the same code, three lines lower
    d = compare.diff(a, b)
    assert d["findings"]["added"] == d["findings"]["removed"] == []


def test_the_same_input_judged_by_other_rules_says_so():
    a = record_of(SQLI)
    b = copy.deepcopy(a)
    b["result"]["fingerprint"]["rules"] = {**a["result"]["fingerprint"]["rules"], "analyser": "9.9.9"}
    b["result"]["fingerprint"]["digest"] = "b" * 64
    b["result"]["findings"] = b["result"]["findings"][:-1]
    d = compare.diff(a, b)
    assert d["same_input"] is True and d["rules"]["analyser"]["b"] == "9.9.9"
    assert "rules changed: analyser" in d["summary"] and d["findings"]["removed"]


def test_a_stricter_or_softer_verdict_is_named():
    a, b = record_of(CLEAN), copy.deepcopy(record_of(CLEAN))
    b["result"]["verdict"] = "FAIL"
    assert compare.diff(a, b)["verdict"]["direction"] == "stricter"
    assert compare.diff(b, a)["verdict"]["direction"] == "softer"


def test_a_run_stored_before_the_fingerprint_body_existed_still_compares():
    a, b = {"id": "a", "result": {"verdict": "PASS", "findings": []}}, {"id": "b", "result": {"verdict": "FAIL"}}
    d = compare.diff(a, b)
    assert d["same_input"] is False and d["verdict"]["direction"] == "stricter"


def test_the_pages_render_with_odd_text_in_them():
    d = compare.diff(record_of(SQLI), record_of(CLEAN))
    d["findings"]["added"] = [{"rule": "<script>", "severity": "high", "message": "a <b>&</b>", "count": 2}]
    html = templates.compare_page(d)
    assert "Two runs compared" in html and "<script>" not in html and "&lt;script&gt;" in html and "(x2)" in html
    page = templates.delete_page({"id": "abc"}, "kept for a while", team=False)
    assert "cannot be undone" in page and "What goes" in page and "/r/abc/delete" in page and "kept for a while" in page
    assert "audit row stays" in templates.delete_page({"id": "abc"}, team=True)


# over HTTP ---------------------------------------------------------------------------------------------

class Doors(ServerCase):
    def run_json(self, material, cookie=None, unique=True):
        # the store is process-wide and one material is one record: a run of its own, unless a test wants to share
        material = f"{material}# {secrets.token_hex(6)}\n" if unique else material
        status, headers, raw = self.post("/run", {"material": material, "intent": "analyse"}, cookie=cookie)
        assert status == 200, raw
        data = json.loads(raw)
        return data["fingerprint"]["id"], self.cookie_of(headers) or cookie

    def delete(self, path, cookie=None):
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", method="DELETE",
                                         headers=self._who(cookie, {}))
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    # compare

    def test_a_visitor_compares_two_of_their_own_runs(self):
        a, cookie = self.run_json(SQLI)
        b, _c = self.run_json(CLEAN, cookie)
        status, raw = self.get(f"/api/compare?a={a}&b={b}", cookie)
        data = json.loads(raw)
        assert status == 200 and data["a"]["id"] == a and data["same_input"] is False and data["findings"]["removed"]
        status, page = self.get(f"/compare?a={a}&b={b}", cookie)
        assert status == 200 and "Two runs compared" in page.decode() and a in page.decode()

    def test_a_run_that_is_not_yours_is_the_same_404_as_one_that_does_not_exist(self):
        mine, cookie = self.run_json(SQLI)
        theirs, _other = self.run_json(CLEAN)
        answers = {self.get(f"/api/compare?a={mine}&b={theirs}", cookie),
                   self.get(f"/api/compare?a={mine}&b=0000000000000000", cookie),
                   self.get(f"/api/compare?a=0000000000000000&b={mine}", cookie)}
        assert len(answers) == 1 and next(iter(answers))[0] == 404
        assert self.get(f"/compare?a={mine}&b={theirs}", cookie)[0] == 404
        assert self.get(f"/api/compare?a={mine}&b={mine}")[0] == 404                       # a stranger

    def test_naming_two_runs_is_required(self):
        run_id, cookie = self.run_json(SQLI)
        assert self.get(f"/api/compare?a={run_id}", cookie)[0] == 400
        assert self.get("/api/compare", cookie)[0] == 400

    def test_the_report_page_offers_the_comparison_and_the_deletion(self):
        run_id, cookie = self.run_json(SQLI)
        page = self.get(f"/r/{run_id}", cookie)[1].decode()
        assert f'name="a" value="{run_id}"' in page and 'action="/compare"' in page and 'pattern="[0-9a-f]{16}"' in page
        assert f"/r/{run_id}/delete" in page

    # delete

    def test_the_confirmation_page_explains_and_deletes_nothing(self):
        run_id, cookie = self.run_json(SQLI)
        status, page = self.get(f"/r/{run_id}/delete", cookie)
        text = page.decode()
        assert status == 200 and "cannot be undone" in text and "What goes" in text and "What does not go" in text
        assert f'method="post" action="/r/{run_id}/delete"' in text
        assert self.get(f"/r/{run_id}", cookie)[0] == 200                      # looking is not deleting

    def test_deleting_removes_the_run_from_every_door(self):
        run_id, cookie = self.run_json(SQLI)
        status, _h, raw = self.post(f"/r/{run_id}/delete", {}, cookie)
        assert status == 200 and "Run deleted" in raw.decode()
        for path in (f"/r/{run_id}", f"/api/runs/{run_id}.json", f"/api/runs/{run_id}.md", f"/api/verify/{run_id}",
                     f"/api/runs/{run_id}.sarif", f"/r/{run_id}/delete"):
            assert self.get(path, cookie)[0] == 404, path
        assert run_id not in self.get("/api/runs", cookie)[1].decode()
        assert server.RUNS.get(run_id) is None

    def test_nobody_else_can_delete_it(self):
        run_id, cookie = self.run_json(SQLI)
        _other_id, other = self.run_json(CLEAN)
        assert self.post(f"/r/{run_id}/delete", {}, other)[0] == 404            # another visitor
        assert self.post(f"/r/{run_id}/delete", {})[0] == 404                   # a stranger
        assert self.delete(f"/api/runs/{run_id}", other)[0] == 404
        assert self.get(f"/r/{run_id}", cookie)[0] == 200

    def test_a_post_from_another_site_deletes_nothing(self):
        run_id, cookie = self.run_json(SQLI)
        status, _h, raw = self.post(f"/r/{run_id}/delete", {}, cookie, headers={"Origin": "https://evil.example"})
        assert status == 403 and "another site" in raw.decode()
        assert self.get(f"/r/{run_id}", cookie)[0] == 200
        ok, _h2, _r = self.post(f"/r/{run_id}/delete", {}, cookie, headers={"Origin": f"http://127.0.0.1:{self.port}"})
        assert ok == 200

    def test_two_visitors_with_the_same_material_each_remove_only_their_own_claim(self):
        shared = f"{SQLI}# {secrets.token_hex(6)}\n"
        run_id, first = self.run_json(shared, unique=False)
        again, second = self.run_json(shared, unique=False)
        assert again == run_id and first != second                              # one record, two owners
        _s, _h, raw = self.post(f"/r/{run_id}/delete", {}, first)
        assert "Removed from your runs" in raw.decode() and "their copy stays" in raw.decode()
        assert self.get(f"/r/{run_id}", first)[0] == 404
        assert self.get(f"/r/{run_id}", second)[0] == 200
        _s, _h, raw = self.post(f"/r/{run_id}/delete", {}, second)
        assert "Run deleted" in raw.decode() and server.RUNS.get(run_id) is None

    def test_the_pages_own_example_cannot_be_deleted(self):
        run_id, cookie = self.run_json(demo.EXAMPLE_MATERIAL, unique=False)
        status, _h, raw = self.post(f"/r/{run_id}/delete", {}, cookie)
        assert status == 403 and "example cannot be deleted" in raw.decode()
        assert server.RUNS.get(run_id) is not None

    def test_the_api_delete_works_for_the_owner_token_and_says_what_happened(self):
        run_id, cookie = self.run_json(SQLI)
        assert self.delete(f"/api/runs/{run_id}")[0] == 401
        status, raw = self.delete(f"/api/runs/{run_id}", cookie)
        assert status == 200 and json.loads(raw) == {"deleted": True}
        assert self.delete(f"/api/runs/{run_id}", cookie)[0] == 404