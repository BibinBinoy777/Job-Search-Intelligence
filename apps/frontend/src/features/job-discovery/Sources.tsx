import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Database,
  RefreshCw,
  ArrowUpRight,
  CheckCircle2,
  AlertTriangle,
} from "lucide-react";
import { api } from "../../services/api-client";
import type { IngestionRun, SourceHealth, Page } from "../../types";
import AutomationOperations from "../automation/Operations";
import {
  Empty,
  ErrorBox,
  Loading,
  PageHeading,
  Pagination,
  label,
} from "../../components/ui";

const time = (value?: string | null) =>
  value ? new Date(value).toLocaleString() : "Not recorded";
export default function SourcesPage() {
  const client = useQueryClient();
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const health = useQuery({
    queryKey: ["source-health"],
    queryFn: () => api<SourceHealth>("/sources/status"),
    refetchInterval: (q) =>
      q.state.data?.sources.some((s) =>
        ["queued", "running"].includes(s.latest_run?.status || ""),
      )
        ? 5000
        : false,
  });
  const runs = useQuery({
    queryKey: ["ingestion-runs", page],
    queryFn: () =>
      api<Page<IngestionRun>>(`/ingestion/runs?page=${page}&page_size=12`),
    refetchInterval: health.data?.sources.some((s) =>
      ["queued", "running"].includes(s.latest_run?.status || ""),
    )
      ? 5000
      : false,
  });
  const sync = useMutation({
    mutationFn: (data: { source_id: string; resume_run_id?: string }) =>
      api<IngestionRun>("/ingestion/sync", "POST", data),
    onSuccess: (r) => {
      setNotice(
        `Synchronization queued (${r.id.slice(0, 8)}). A worker must process it before results are available.`,
      );
      client.invalidateQueries({ queryKey: ["source-health"] });
      client.invalidateQueries({ queryKey: ["ingestion-runs"] });
    },
  });
  return (
    <>
      {health.data?.can_sync && (
        <AutomationOperations
          sources={health.data.sources.map((s) => s.source)}
        />
      )}
      <PageHeading
        eyebrow="REAL SOURCES. VISIBLE EVIDENCE."
        title="Know where your jobs come from."
        description="Source health, collection history, and the details behind every synchronization."
        action={
          <button
            className="secondary"
            onClick={() => {
              health.refetch();
              runs.refetch();
            }}
          >
            <RefreshCw size={16} />
            Refresh status
          </button>
        }
      />
      <div className="discovery-notice">
        <Database size={17} />
        <span>
          Background collection is independent of your workspace. Previously
          verified jobs remain searchable during temporary source failures,
          within the freshness window.
        </span>
      </div>
      {health.isPending ? (
        <Loading />
      ) : health.error ? (
        <ErrorBox error={health.error} retry={() => health.refetch()} />
      ) : !health.data?.sources.length ? (
        <section className="panel">
          <Empty title="No sources configured yet">
            An operator can configure the supported Himalayas adapter using the
            documented local command. No network synchronization has been
            assumed.
          </Empty>
        </section>
      ) : (
        <div className="source-grid">
          {health.data.sources.map(
            ({ source: s, latest_run: r, stored_jobs, available_jobs }) => (
              <section className="panel source-panel" key={s.id}>
                <div className="source-title">
                  <span className="stat-icon green">
                    <Database size={20} />
                  </span>
                  <div>
                    <h2>{s.name}</h2>
                    <small>
                      {s.adapter_key
                        ? `Installed adapter · ${s.source_type}`
                        : "Manual records · no network adapter"}
                    </small>
                  </div>
                  <span className={`badge ${s.operational_status}`}>
                    {label(s.operational_status)}
                  </span>
                </div>
                <div className="source-counts">
                  <div>
                    <strong>{available_jobs}</strong>
                    <span>Visible jobs</span>
                  </div>
                  <div>
                    <strong>{stored_jobs}</strong>
                    <span>Stored records</span>
                  </div>
                  <div>
                    <strong>{r?.inserted ?? "—"}</strong>
                    <span>Added in last run</span>
                  </div>
                </div>
                <dl>
                  <dt>Last attempt</dt>
                  <dd>{time(s.last_sync_at)}</dd>
                  <dt>Last successful batch</dt>
                  <dd>{time(s.last_success_at)}</dd>
                  <dt>Last complete feed walk</dt>
                  <dd>{time(s.last_full_sync_at)}</dd>
                  <dt>Next scheduled attempt</dt>
                  <dd>
                    {s.schedule_hours
                      ? time(s.next_sync_at)
                      : "Scheduling disabled"}
                  </dd>
                  <dt>Source cooldown until</dt>
                  <dd>{time(s.not_before_at)}</dd>
                </dl>
                {s.error_code && (
                  <div className="source-warning" role="status">
                    <AlertTriangle size={16} />
                    Last error: {label(s.error_code)}. This is not a successful
                    empty sync.
                  </div>
                )}
                {r?.status === "limited" && (
                  <p className="source-help">
                    Page limit reached; this batch succeeded. More source pages
                    remain. This does not represent a complete source mirror.
                  </p>
                )}
                {s.adapter_key === "himalayas" && (
                  <a
                    className="text-button"
                    href="https://himalayas.app/docs/remote-jobs-api"
                    target="_blank"
                    rel="noreferrer"
                  >
                    Data sourced from Himalayas <ArrowUpRight size={14} />
                  </a>
                )}
                {health.data.can_sync && s.adapter_key && (
                  <div className="source-controls">
                    <button
                      className="primary"
                      disabled={
                        !s.enabled ||
                        sync.isPending ||
                        ["queued", "running"].includes(r?.status || "")
                      }
                      onClick={() => sync.mutate({ source_id: s.id })}
                    >
                      Queue synchronization
                    </button>
                    {r?.has_more &&
                      !["queued", "running"].includes(r.status) && (
                        <button
                          className="secondary"
                          disabled={sync.isPending}
                          onClick={() =>
                            sync.mutate({
                              source_id: s.id,
                              resume_run_id: r.id,
                            })
                          }
                        >
                          Resume after last page
                        </button>
                      )}
                  </div>
                )}
              </section>
            ),
          )}
        </div>
      )}
      {notice && (
        <p className="success" role="status">
          {notice}
        </p>
      )}
      {sync.error && <ErrorBox error={sync.error} />}
      <section className="panel run-panel">
        <div className="section-heading">
          <div>
            <h2>Ingestion history</h2>
            <p>
              Actual persisted runs. A queued task has not fetched any jobs yet.
            </p>
          </div>
        </div>
        {runs.isPending ? (
          <Loading />
        ) : runs.error ? (
          <ErrorBox error={runs.error} retry={() => runs.refetch()} />
        ) : !runs.data?.items.length ? (
          <Empty title="No ingestion runs recorded">
            Run history will appear only after a synchronization is queued by an
            operator.
          </Empty>
        ) : (
          <>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Source / started</th>
                    <th>Outcome</th>
                    <th>Fetched</th>
                    <th>Inserted</th>
                    <th>Updated</th>
                    <th>Unchanged</th>
                    <th>Rejected / skipped</th>
                    <th>Retries</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.data.items.map((r) => (
                    <tr key={r.id}>
                      <td>
                        <button
                          className="text-button"
                          onClick={() =>
                            setSelected(selected === r.id ? null : r.id)
                          }
                        >
                          {r.source.name} · {r.id.slice(0, 8)}
                        </button>
                        <small>{time(r.started_at || r.created_at)}</small>
                      </td>
                      <td>
                        <span className={`badge ${r.status}`}>
                          {label(r.status)}
                        </span>
                      </td>
                      <td>{r.fetched}</td>
                      <td>{r.inserted}</td>
                      <td>{r.updated}</td>
                      <td>{r.unchanged}</td>
                      <td>
                        {r.rejected} / {r.skipped}
                      </td>
                      <td>{r.retried}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination page={page} total={runs.data.total} change={setPage} />
          </>
        )}
      </section>
      {selected && <RunDetails id={selected} />}
      <p className="muted small">
        Probable cross-source duplicate pairs:{" "}
        {health.data?.probable_duplicate_pairs ?? "—"}. Candidates are flagged
        for review and never merged automatically.
      </p>
    </>
  );
}

function RunDetails({ id }: { id: string }) {
  const [page, setPage] = useState(1);
  const run = useQuery({
    queryKey: ["ingestion-run", id],
    queryFn: () => api<IngestionRun>(`/ingestion/runs/${id}`),
  });
  const records = useQuery({
    queryKey: ["ingestion-records", id, page],
    queryFn: () =>
      api<
        Page<{
          id: string;
          page_number: number;
          record_number: number;
          outcome: string;
          error_code: string | null;
        }>
      >(`/ingestion/runs/${id}/records?page=${page}&page_size=12`),
  });
  return (
    <section className="panel form-panel">
      <h2>Run {id.slice(0, 8)}</h2>
      {run.error ? (
        <ErrorBox error={run.error} />
      ) : (
        run.data && (
          <>
            <p className="small muted">
              {run.data.pages} committed pages · {run.data.accepted} accepted ·{" "}
              {run.data.duplicates} repeated deliveries · {run.data.errors}{" "}
              errors
            </p>
            <p className="source-reconciled">
              <CheckCircle2 size={15} />
              {run.data.reconciled === null
                ? "Reconciliation waits for this run to finish."
                : run.data.reconciled
                  ? "Record ledger agrees with the run counters."
                  : "Run accounting requires attention."}
            </p>
            {run.data.error_code && (
              <ErrorBox error={new Error(label(run.data.error_code))} />
            )}
          </>
        )
      )}
      {records.isPending ? (
        <Loading />
      ) : records.error ? (
        <ErrorBox error={records.error} />
      ) : (
        <>
          <div className="record-grid">
            {records.data?.items.map((r) => (
              <div key={r.id}>
                <span>
                  Page {r.page_number} · record {r.record_number + 1}
                </span>
                <strong>{label(r.outcome)}</strong>
                {r.error_code && <small>{label(r.error_code)}</small>}
              </div>
            ))}
          </div>
          <Pagination
            page={page}
            total={records.data?.total || 0}
            change={setPage}
          />
        </>
      )}
    </section>
  );
}
