import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { fixtures, mockApi } from "../test/mockApi";
import WorkspaceView, { QUESTIONNAIRE_NOTICE, UPLOAD_NOTICE } from "./Workspace";

const props = { workspace: fixtures.workspace, onGone: () => {} };

describe("Workspace", () => {
  it("lists documents with their metadata in words and the upload notice", async () => {
    mockApi({ "GET /api/documents": fixtures.documents, "GET /api/questionnaires": [] });
    render(<WorkspaceView {...props} />);
    const row = await screen.findByRole("row", { name: /access-control-policy\.docx/ });
    expect(within(row).getByText("policy")).toBeInTheDocument();
    expect(within(row).getByText("evidence")).toBeInTheDocument();
    expect(screen.getByText(UPLOAD_NOTICE)).toBeInTheDocument();
  });

  it("offers no metadata edit for the visitor's own answer (adversary-2 I1)", async () => {
    const answer = { ...fixtures.documents[0], id: "d2", filename: "answer-001.txt", source: "statement" as const, kind: "statement" as const };
    mockApi({ "GET /api/documents": [...fixtures.documents, answer], "GET /api/questionnaires": [] });
    render(<WorkspaceView {...props} />);
    const row = await screen.findByRole("row", { name: /answer-001\.txt/ });
    expect(within(row).queryByRole("button", { name: /^Edit / })).not.toBeInTheDocument();
    expect(within(row).getByText("your answer")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit access-control-policy.docx" })).toBeInTheDocument();
  });

  it("shows a refused upload's sentence under the control", async () => {
    mockApi({
      "GET /api/documents": [],
      "GET /api/questionnaires": [],
      "POST /api/documents": new Response(JSON.stringify({ detail: "Files must be 4 MB or smaller." }), { status: 422 }),
    });
    render(<WorkspaceView {...props} />);
    const input = await screen.findByLabelText("upload documents");
    await userEvent.upload(input, new File(["x"], "big.pdf"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Error: Files must be 4 MB or smaller.");
  });

  it("previews the detected mapping, lets the visitor correct a column and confirm", async () => {
    let sent: unknown = null;
    mockApi({
      "GET /api/documents": [],
      "GET /api/questionnaires": [],
      "POST /api/questionnaires": fixtures.questionnaire,
      "PUT /api/questionnaires/q1/mapping": (init?: RequestInit) => {
        sent = JSON.parse(String(init?.body));
        return { ...fixtures.questionnaire, mapping: sent, item_count: 20 };
      },
    });
    render(<WorkspaceView {...props} />);
    await userEvent.upload(await screen.findByLabelText("upload a questionnaire"), new File(["x"], "v05.xlsx"));
    expect(await screen.findByRole("cell", { name: /documented security program/ })).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("comments column"), "D");
    await userEvent.click(screen.getByRole("button", { name: "Confirm mapping" }));
    expect(sent).toMatchObject({ sheet: "Controls", header_row: 1, question_col: "B", comments_col: "D" });
    expect(await screen.findByText("20 questions")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start run" })).toHaveFocus();
  });

  it("an override reports how many answers were decided again", async () => {
    mockApi({
      "GET /api/documents": fixtures.documents,
      "GET /api/questionnaires": [],
      "PATCH /api/documents/d1": { ...fixtures.documents[0], status: "draft", metadata_source: "user", redecided: 3 },
    });
    render(<WorkspaceView {...props} />);
    await userEvent.click(await screen.findByRole("button", { name: "Edit access-control-policy.docx" }));
    await userEvent.selectOptions(screen.getByLabelText("status"), "draft");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("3 answers decided again")).toBeInTheDocument();
  });

  it("ties the notice and a refusal to the upload input, and Save returns focus to Edit", async () => {
    mockApi({
      "GET /api/documents": fixtures.documents,
      "GET /api/questionnaires": [],
      "POST /api/documents": new Response("too big", { status: 413 }),
      "PATCH /api/documents/d1": { ...fixtures.documents[0], redecided: 1 },
    });
    render(<WorkspaceView {...props} />);
    const input = await screen.findByLabelText("upload documents");
    expect(input).toHaveAccessibleDescription(UPLOAD_NOTICE);
    expect(screen.getByLabelText("upload a questionnaire")).toHaveAccessibleDescription(QUESTIONNAIRE_NOTICE);
    await userEvent.upload(input, new File(["x"], "big.pdf"));
    await screen.findByRole("alert");
    expect(input).toHaveAccessibleDescription(`${UPLOAD_NOTICE} Error: Files must be 4 MB or smaller. (big.pdf)`);
    const edit = screen.getByRole("button", { name: "Edit access-control-policy.docx" });
    await userEvent.click(edit);
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled(); // nothing changed yet
    await userEvent.selectOptions(screen.getByLabelText("kind"), "report");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("1 answer decided again")).toBeInTheDocument();
    expect(edit).toHaveFocus();
  });

  it("a sample questionnaire loaded twice is listed once", async () => {
    mockApi({
      "GET /api/documents": [],
      "GET /api/questionnaires": [],
      "POST /api/questionnaires/sample/vsq-a": { ...fixtures.questionnaire, filename: "vsq-a.xlsx", source: "sample", item_count: 64 },
    });
    render(<WorkspaceView {...props} />);
    await screen.findByLabelText("upload documents");
    await userEvent.keyboard("q");
    expect(await screen.findByText("64 questions")).toBeInTheDocument();
    await userEvent.keyboard("q");
    expect(screen.queryByText(/questionnaires in this workspace/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start run" })).toBeInTheDocument();
  });

  it("uses the approved notices, each on its own input", async () => {
    mockApi({ "GET /api/documents": [], "GET /api/questionnaires": [] });
    render(<WorkspaceView {...props} />);
    expect(UPLOAD_NOTICE).toBe(
      "Names and secrets are replaced before anything reaches a model. Known gaps: a single first name, names in lower case, names written 'Last, First', and names in all capitals with accents may not be caught. Remove anything sensitive you can't share.",
    );
    expect(QUESTIONNAIRE_NOTICE).toBe(
      "Questionnaires are stored and sent to the model as written, without redaction. Don't upload one that contains personal data.",
    );
    expect(await screen.findByLabelText("upload documents")).toHaveAccessibleDescription(UPLOAD_NOTICE);
    expect(screen.getByLabelText("upload a questionnaire")).toHaveAccessibleDescription(QUESTIONNAIRE_NOTICE);
  });

  it("a closed edit form discards its change, so the next Save sends only the new edit", async () => {
    let sent: unknown = null;
    mockApi({
      "GET /api/documents": fixtures.documents,
      "GET /api/questionnaires": [],
      "PATCH /api/documents/d1": (init?: RequestInit) => {
        sent = JSON.parse(String(init?.body));
        return { ...fixtures.documents[0], kind: "report", redecided: 0 };
      },
    });
    render(<WorkspaceView {...props} />);
    const edit = await screen.findByRole("button", { name: "Edit access-control-policy.docx" });
    await userEvent.click(edit);
    await userEvent.selectOptions(screen.getByLabelText("status"), "draft");
    await userEvent.click(edit); // close without saving
    await userEvent.click(edit);
    expect(screen.getByLabelText("status")).toHaveValue("final");
    await userEvent.selectOptions(screen.getByLabelText("kind"), "report");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByText("0 answers decided again");
    expect(sent).toEqual({ kind: "report" });
  });

  it("shows a refused metadata save inside that row's form", async () => {
    mockApi({
      "GET /api/documents": fixtures.documents,
      "GET /api/questionnaires": [],
      "PATCH /api/documents/d1": new Response(JSON.stringify({ detail: "Input should be a valid date" }), { status: 422 }),
    });
    render(<WorkspaceView {...props} />);
    await userEvent.click(await screen.findByRole("button", { name: "Edit access-control-policy.docx" }));
    await userEvent.selectOptions(screen.getByLabelText("status"), "draft");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    const form = screen.getByRole("form", { name: "metadata of access-control-policy.docx" });
    expect(await screen.findByRole("alert")).toHaveTextContent("Error: Input should be a valid date");
    expect(form).toHaveAccessibleDescription("Error: Input should be a valid date");
  });

  it("a 404 on load means the workspace is gone", async () => {
    const onGone = vi.fn();
    const gone = () => new Response(JSON.stringify({ detail: "This workspace has expired; reload the page." }), { status: 404 });
    mockApi({ "GET /api/documents": gone, "GET /api/questionnaires": gone });
    render(<WorkspaceView workspace={fixtures.workspace} onGone={onGone} />);
    await vi.waitFor(() => expect(onGone).toHaveBeenCalled());
  });

  it("lists the questionnaires; the visitor chooses one and deletes another, and a refused delete says why", async () => {
    const older = { ...fixtures.questionnaire, id: "q2", filename: "older.csv", item_count: 12 };
    const used = { ...fixtures.questionnaire, id: "q3", filename: "used.xlsx", item_count: 30, latest_run_id: "r9" };
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const calls = mockApi({
      "GET /api/documents": [],
      "GET /api/questionnaires": [fixtures.questionnaire, older, used],
      "DELETE /api/questionnaires/q1": new Response(null, { status: 204 }),
      "DELETE /api/questionnaires/q3": new Response(
        JSON.stringify({ detail: "A run used this questionnaire; reset the workspace to start over." }), { status: 409 },
      ),
    });
    render(<WorkspaceView {...props} />);
    const list = await screen.findByRole("table", { name: "questionnaires (3 of 5)" });
    expect(within(list).getByRole("row", { name: /v05\.xlsx/ })).toHaveAttribute("aria-current", "true");
    // choose by keyboard: Tab to the row's Open button and press Enter
    within(list).getByRole("button", { name: "Open older.csv" }).focus();
    await userEvent.keyboard("{Enter}");
    expect(screen.getByText("12 questions")).toBeInTheDocument();
    expect(within(list).getByRole("row", { name: /older\.csv/ })).toHaveAttribute("aria-current", "true");
    expect(within(list).getByRole("button", { name: "older.csv is shown" })).toHaveFocus(); // the name holds "shown"
    await userEvent.click(within(list).getByRole("button", { name: "Delete used.xlsx" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Error: A run used this questionnaire; reset the workspace to start over.");
    expect(within(list).getByRole("row", { name: /used\.xlsx/ })).toBeInTheDocument();
    await userEvent.click(within(list).getByRole("button", { name: "Delete v05.xlsx" }));
    expect(await screen.findByRole("table", { name: "questionnaires (2 of 5)" })).toBeInTheDocument();
    expect(screen.queryByRole("row", { name: /v05\.xlsx/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(calls.filter((c) => c.startsWith("DELETE"))).toEqual(["DELETE /api/questionnaires/q3", "DELETE /api/questionnaires/q1"]);
  });

  it("an upload that lands while a delete is pending stays listed, and the refused delete's error clears", async () => {
    const older = { ...fixtures.questionnaire, id: "q2", filename: "older.csv", item_count: 12 };
    const fresh = { ...fixtures.questionnaire, id: "q4", filename: "fresh.csv", item_count: 7 };
    vi.spyOn(window, "confirm").mockReturnValue(true);
    let finish: (r: Response) => void = () => {};
    let n = 0;
    mockApi({
      "GET /api/documents": [],
      "GET /api/questionnaires": [fixtures.questionnaire, older],
      "POST /api/questionnaires": fresh,
      "DELETE /api/questionnaires/q2": () =>
        ++n === 1
          ? new Response(JSON.stringify({ detail: "A run used this questionnaire." }), { status: 409 })
          : new Promise<Response>((resolve) => { finish = resolve; }),
    });
    render(<WorkspaceView {...props} />);
    const list = await screen.findByRole("table", { name: "questionnaires (2 of 5)" });
    await userEvent.click(within(list).getByRole("button", { name: "Delete older.csv" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("A run used this questionnaire.");
    await userEvent.click(within(list).getByRole("button", { name: "Delete older.csv" })); // pending
    await userEvent.upload(screen.getByLabelText("upload a questionnaire"), new File(["x"], "fresh.csv"));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    await act(async () => finish(new Response(null, { status: 204 })));
    expect(await screen.findByRole("table", { name: "questionnaires (2 of 5)" })).toBeInTheDocument();
    expect(screen.getByRole("row", { name: /fresh\.csv/ })).toHaveAttribute("aria-current", "true");
    expect(screen.queryByRole("row", { name: /older\.csv/ })).not.toBeInTheDocument();
  });

  it("deleting the shown questionnaire shows the next one", async () => {
    const older = { ...fixtures.questionnaire, id: "q2", filename: "older.csv", item_count: 12 };
    vi.spyOn(window, "confirm").mockReturnValue(true);
    mockApi({
      "GET /api/documents": [],
      "GET /api/questionnaires": [{ ...fixtures.questionnaire, item_count: 20 }, older],
      "DELETE /api/questionnaires/q1": new Response(null, { status: 204 }),
    });
    render(<WorkspaceView {...props} />);
    await userEvent.click(await screen.findByRole("button", { name: "Delete v05.xlsx" }));
    expect(await screen.findByText("12 questions")).toBeInTheDocument();
  });

  it("the header row accepts a cleared field and refuses rows past 1000 before sending", async () => {
    let sent: { header_row?: number } | null = null;
    mockApi({
      "GET /api/documents": [],
      "GET /api/questionnaires": [fixtures.questionnaire],
      "PUT /api/questionnaires/q1/mapping": (init?: RequestInit) => {
        sent = JSON.parse(String(init?.body));
        return { ...fixtures.questionnaire, item_count: 5 };
      },
    });
    render(<WorkspaceView {...props} />);
    const row = await screen.findByLabelText("header row");
    expect(row).toHaveAttribute("max", "1000");
    await userEvent.clear(row);
    await userEvent.type(row, "3");
    await userEvent.click(screen.getByRole("button", { name: "Confirm mapping" }));
    await screen.findByText("5 questions");
    expect(sent).toMatchObject({ header_row: 3 });
  });

  it("Enter on a focused select submits the form its hint is on", async () => {
    let sent = false;
    mockApi({
      "GET /api/documents": [],
      "GET /api/questionnaires": [fixtures.questionnaire],
      "PUT /api/questionnaires/q1/mapping": () => { sent = true; return { ...fixtures.questionnaire, item_count: 5 }; },
    });
    render(<WorkspaceView {...props} />);
    (await screen.findByLabelText("topic column")).focus();
    await userEvent.keyboard("{Enter}");
    await screen.findByText("5 questions");
    expect(sent).toBe(true);
  });
});
