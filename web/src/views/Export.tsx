import { useEffect, useRef, useState } from "react";
import { Shell, goneOn404, type ViewProps } from "../components/Shell";
import { ErrorLine, Kbd } from "../components/ui";
import { api, type RunRowsOut } from "../lib/api";
import { useKeys } from "../lib/keys";

export default function ExportView({ workspace, onGone, runId }: ViewProps & { runId: string }) {
  const [data, setData] = useState<RunRowsOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    api.runAnswers(runId).then(
      (d) => { if (alive) setData(d); },
      (e) => { if (alive) setError(goneOn404(e, onGone)); },
    );
    return () => { alive = false; setData(null); };
  }, [runId, onGone]);
  const url = api.exportUrl(runId);
  const link = useRef<HTMLAnchorElement>(null);
  useKeys({ e: () => link.current?.click() }); // the same download link, so one path decides what a click does
  const rows = data?.rows ?? [];
  const approved = rows.filter((r) => r.answer?.approved).length;
  const draft = rows.filter((r) => r.answer && !r.answer.approved).length;
  const unanswered = rows.length - approved - draft;
  return (
    <Shell mode="EXPORT" cursor="" hints={[["e", "export"], ["?", "all keys"]]} expiresAt={workspace.expires_at} runId={runId}>
      <div className="mx-auto max-w-3xl space-y-3 p-4 text-sm">
        <h1 className="border-b border-ink text-xs font-medium text-ink-2">export</h1>
        <ErrorLine message={error} />
        {data && <p className="tabular-nums">{approved} approved · {draft} draft · {unanswered} unanswered</p>}
        <p className="text-ink-2">
          The file you uploaded comes back with the answer column filled and three columns added: Status, Sources and
          Notes. Unapproved answers are exported marked "Draft, not approved". A csv comes back as csv. If you ran a
          gap check, an xlsx also gets a Gap report sheet with the latest gap check that is done, its scope and its date.
        </p>
        <p className="text-xs text-ink-3">Embedded images and charts are not kept in an exported workbook (an openpyxl limit).</p>
        <a ref={link} href={url} download aria-keyshortcuts="e" className="inline-flex h-7 items-center gap-2 bg-chrome px-2 text-sm font-medium text-on-chrome hover:bg-neutral-800">
          <Kbd>e</Kbd><span>Export</span>
        </a>
      </div>
    </Shell>
  );
}
