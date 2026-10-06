import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { fixtures, mockApi } from "../test/mockApi";
import WorkspaceView, { UPLOAD_NOTICE } from "./Workspace";

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
    expect(screen.getByLabelText("upload a questionnaire")).toHaveAccessibleDescription(UPLOAD_NOTICE);
    await userEvent.upload(input, new File(["x"], "big.pdf"));
    await screen.findByRole("alert");
    expect(input).toHaveAccessibleDescription(`${UPLOAD_NOTICE} Error: Files must be 4 MB or smaller. (big.pdf)`);
    const edit = screen.getByRole("button", { name: "Edit access-control-policy.docx" });
    await userEvent.click(edit);
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
});
