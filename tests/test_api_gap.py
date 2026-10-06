import io
import json
import threading
import uuid
from datetime import timedelta

import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import Session

from app import csf, runs
from app.api.deps import get_llm
from app.db.models import Answer, DocumentLine, Item, Questionnaire, Run, Workspace
from app.export import FOOTER
from app.main import app
from app.services.ip_limits import LIMITS
from tests import factories as f
from tests.apiclient import visitor
from tests.fakes import ByStepLLM

LINE = "Backups of data are created, protected, maintained and tested every day."
YES = json.dumps({"passages": [{"passage": 1, "stance": "yes", "quote": LINE, "note": "states it"}]})


def _finish(client: TestClient, run_id: str, llm: object) -> None:
    app.dependency_overrides[get_llm] = lambda: llm
    try:
        for _ in range(60):
            if client.get(f"/api/runs/{run_id}").json()["status"] != "running":
                return
            assert client.post(f"/api/runs/{run_id}/step").status_code == 200
        raise AssertionError("the run did not finish")
    finally:
        app.dependency_overrides.pop(get_llm, None)


def _policy(s: Session, ws_id: uuid.UUID, status: str = "final") -> None:
    """One stored policy line, as an upload leaves it (document, line, chunk)."""
    doc = f.document(s, s.get_one(Workspace, ws_id), filename="backup-policy.docx", status=status)
    s.add(DocumentLine(document_id=doc.id, n=1, text=LINE))
    f.chunk(s, doc, line_start=1, line_end=1, text=LINE)
    s.commit()


def test_the_view_lists_every_outcome_and_labels_only_what_was_checked(db: Engine) -> None:
    client, _ = visitor(db)
    before = client.get("/api/gap/core").json()
    assert before["run"] is None and len(before["rows"]) == 106
    assert {r["label"] for r in before["rows"]} == {None}
    tiers = [r["tier"] for r in before["rows"]]
    assert (tiers.count("checked"), tiers.count("ask"), tiers.count("not_checked")) == (31, 5, 70)
    assert before["rows"][0]["outcome"] == csf.framework().outcomes[0].outcome  # NIST's text, verbatim
    with Session(db) as s:
        assert s.scalar(select(func.count()).select_from(Questionnaire)) == 0  # the view writes nothing
    run = client.post("/api/gap/core/run").json()
    _finish(client, run["id"], ByStepLLM({}))  # no documents: no part has a passage, nothing is called
    after = client.get("/api/gap/core").json()
    rows = {r["csf_id"]: r for r in after["rows"]}
    assert (rows["PR.DS-11"]["label"], rows["PR.DS-11"]["explanation"]) == (
        "gap",
        "No evidence: parts 1, 2, 3, 4.",
    )
    assert (rows["GV.RM-02"]["label"], rows["GV.RM-02"]["explanation"]) == ("not_answered", None)
    assert all(
        r["label"] is None and r["item_id"] is None for r in after["rows"] if r["tier"] == "not_checked"
    )
    assert after["run"]["status"] == "done" and after["controls_url"] == csf.CONTROLS_URL


def test_a_function_scope_lists_its_own_outcomes_and_runs_only_them(db: Engine) -> None:
    client, _ = visitor(db)
    rows = client.get("/api/gap/recover").json()["rows"]
    assert {r["function"] for r in rows} == {"Recover"}
    assert client.post("/api/gap/recover/run").json()["total"] == 1  # RC.RP-01: Recover's one checked outcome
    assert client.get("/api/gap/everything").status_code == 422


def test_starting_twice_continues_the_same_run_and_the_questionnaire_stays_built_in(db: Engine) -> None:
    client, _ = visitor(db)
    first = client.post("/api/gap/core/run").json()
    again = client.post("/api/gap/core/run").json()
    assert (again["id"], again["status"]) == (first["id"], "running")
    assert client.get("/api/questionnaires").json() == []  # Plan 3 Ruling 5: never listed or counted


def test_starting_counts_under_the_run_limit(db: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(LIMITS, "run", (1, timedelta(hours=1)))
    client, _ = visitor(db)
    assert client.post("/api/gap/core/run").status_code == 200
    res = client.post("/api/gap/govern/run")
    assert res.status_code == 429 and res.headers["Retry-After"]


def test_another_workspace_sees_none_of_it(db: Engine) -> None:
    client, _ = visitor(db)
    client.post("/api/gap/core/run")
    other, _ = visitor(db)
    assert other.get("/api/gap/core").json()["run"] is None


def test_an_outcomes_evidence_lists_its_parts_with_their_own_citations(db: Engine) -> None:
    client, ws_id = visitor(db)
    with Session(db) as s:
        _policy(s, ws_id, status="draft")
    run = client.post("/api/gap/protect/run").json()
    _finish(client, run["id"], ByStepLLM({"stance": YES}))
    row = next(r for r in client.get("/api/gap/protect").json()["rows"] if r["csf_id"] == "PR.DS-11")
    assert row["label"] == "partly_covered"  # every part rests on a draft
    detail = client.get(f"/api/answers/{row['answer_id']}").json()
    parts = detail["parts"]
    assert [p["n"] for p in parts] == [1, 2, 3, 4]
    assert [p["question"] for p in parts] == list(csf.framework().get("PR.DS-11").parts)
    assert {p["label"] for p in parts} == {"partly_covered"} and not any(p["from_statement"] for p in parts)
    cite = parts[0]["citations"][0]
    assert (cite["quote"], cite["status"], cite["found_in_source"]) == (LINE, "draft", True)  # carry d


def test_the_gap_report_downloads_for_a_gap_run(db: Engine) -> None:
    client, _ = visitor(db)
    run = client.post("/api/gap/recover/run").json()
    _finish(client, run["id"], ByStepLLM({}))
    res = client.get(f"/api/runs/{run['id']}/export")
    assert res.status_code == 200
    assert res.headers["content-disposition"] == 'attachment; filename="csf-2.0-recover-gap-report.xlsx"'
    ws = openpyxl.load_workbook(io.BytesIO(res.content))["Gap report"]
    recover = [o for o in csf.framework().outcomes if o.function == "Recover"]
    assert [ws.cell(n, 1).value for n in range(3, 3 + len(recover))] == [o.id for o in recover]
    assert ws.cell(len(recover) + 4, 1).value == FOOTER
    assert (ws["B1"].value, ws["C1"].value) == ("Scope: recover", f"Run date: {run['started_at'][:10]}")


def test_a_questionnaire_export_carries_the_latest_gap_sheet_only_when_one_exists(db: Engine) -> None:
    client, _ = visitor(db)
    q = client.post("/api/questionnaires/sample/vsq-a").json()
    qrun = client.post(f"/api/questionnaires/{q['id']}/runs").json()  # no step needed: an empty run exports
    before = openpyxl.load_workbook(io.BytesIO(client.get(f"/api/runs/{qrun['id']}/export").content))
    assert "Gap report" not in before.sheetnames  # no gap check yet: the export is unchanged
    gap = client.post("/api/gap/recover/run").json()
    _finish(client, gap["id"], ByStepLLM({}))
    after = openpyxl.load_workbook(io.BytesIO(client.get(f"/api/runs/{qrun['id']}/export").content))
    assert after.sheetnames == [*before.sheetnames, "Gap report"]
    ws = after["Gap report"]
    assert (ws["A1"].value, ws["B1"].value) == ("Possible gap — review it", "Scope: recover")
    assert ws["A3"].value == "RC.RP-01" and ws["D3"].value == "Gap"


def test_two_first_presses_at_once_create_one_run(db: Engine) -> None:
    client, ws_id = visitor(db)
    other = TestClient(app, cookies=client.cookies)
    results: list[dict] = []  # type: ignore[type-arg]
    gate = threading.Barrier(2)

    def press(c: TestClient) -> None:
        gate.wait()
        results.append(c.post("/api/gap/recover/run").json())

    threads = [threading.Thread(target=press, args=(c,)) for c in (client, other)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    with Session(db) as s:
        assert s.scalar(select(func.count()).select_from(Run).where(Run.workspace_id == ws_id)) == 1
    assert len(results) == 2 and results[0]["id"] == results[1]["id"]


def _answer(db: Engine, csf_id: str) -> uuid.UUID:
    with Session(db) as s:
        return s.scalars(
            select(Answer.id).join(Item, Item.id == Answer.item_id).where(Item.csf_id == csf_id)
        ).one()


def test_not_applicable_and_failed_outcomes_carry_no_gap_label(db: Engine) -> None:
    client, _ = visitor(db)
    run = client.post("/api/gap/core/run").json()
    _finish(client, run["id"], ByStepLLM({}))
    na_checked, na_ask, failed = _answer(db, "PR.DS-11"), _answer(db, "GV.RM-02"), _answer(db, "PR.AA-01")
    for aid in (na_checked, na_ask):
        assert (
            client.post(f"/api/answers/{aid}/not-applicable", json={"reason": "not ours"}).status_code == 200
        )
    with Session(db) as s:
        s.execute(update(Answer).where(Answer.id == failed).values(label="unknown", text=runs.FAILED_TEXT))
        s.commit()
    rows = {r["csf_id"]: r for r in client.get("/api/gap/core").json()["rows"]}
    for cid in ("PR.DS-11", "GV.RM-02"):
        assert (rows[cid]["label"], rows[cid]["not_applicable"]) == (None, True)
        assert rows[cid]["explanation"] == "Not applicable: not ours"
    assert (rows["PR.AA-01"]["label"], rows["PR.AA-01"]["not_applicable"]) == (None, False)
    assert (
        rows["PR.AA-01"]["explanation"] == "Not checked: the model call failed twice. Press r to check again."
    )
    sheet = openpyxl.load_workbook(io.BytesIO(client.get(f"/api/runs/{run['id']}/export").content))[
        "Gap report"
    ]
    words = {sheet.cell(n, 1).value: sheet.cell(n, 4).value for n in range(3, 109)}
    assert (words["PR.DS-11"], words["GV.RM-02"], words["PR.AA-01"]) == (
        "Not applicable",
        "Not applicable",
        "Not run yet",
    )


def test_a_stale_part_citation_never_breaks_the_inspector_and_approve_all_skips_not_met(db: Engine) -> None:
    client, _ = visitor(db)
    run = client.post("/api/gap/recover/run").json()
    _finish(client, run["id"], ByStepLLM({}))
    aid = _answer(db, "RC.RP-01")
    with Session(db) as s:  # a failed outcome keeps parts, but its answer is not a result of them
        s.execute(update(Answer).where(Answer.id == aid).values(label="unknown", text=runs.FAILED_TEXT))
        s.commit()
    assert client.get(f"/api/answers/{aid}").json()["parts"] == []
    with Session(db) as s:  # N3: a Not met outcome (verified, No) is not approved in bulk
        s.execute(
            update(Answer)
            .where(Answer.id == aid)
            .values(label="verified", value="No", text="x", citations=[{"quote": "q"}])
        )
        s.commit()
    assert client.post(f"/api/runs/{run['id']}/approve-verified").json()["approved"] == 0
