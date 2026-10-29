import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../services/api-client";
import {
  ErrorBox,
  Field,
  Loading,
  Pagination,
  label,
} from "../../components/ui";
import type { Page } from "../../types";
import type { AutomationStatus, Task } from "./types";

export default function AutomationOperations({
  sources,
}: {
  sources: {
    id: string;
    name: string;
    schedule_hours?: number | null;
    page_limit?: number;
    adapter_key?: string | null;
    enabled?: boolean;
  }[];
}) {
  const client = useQueryClient();
  const [page, setPage] = useState(1);
  const [notice, setNotice] = useState("");
  const status = useQuery({
    queryKey: ["automation-status"],
    queryFn: () => api<AutomationStatus>("/automation/status"),
    refetchInterval: 30000,
  });
  const tasks = useQuery({
    queryKey: ["automation-tasks", page],
    queryFn: () =>
      api<Page<Task>>(`/automation/tasks?page=${page}&page_size=10`),
    refetchInterval: 30000,
  });
  const [deliveryPage, setDeliveryPage] = useState(1);
  const deliveries = useQuery({
    queryKey: ["automation-deliveries", deliveryPage],
    queryFn: () =>
      api<
        Page<{
          id: string;
          channel: string;
          status: string;
          attempts: number;
          error_code: string | null;
          history: unknown[];
        }>
      >(`/automation/deliveries?page=${deliveryPage}&page_size=10`),
    refetchInterval: 30000,
  });
  const mutation = useMutation({
    mutationFn: ({ path, body }: { path: string; body: unknown }) =>
      api(path, path.endsWith("/schedule") ? "PUT" : "POST", body),
    onSuccess: () => {
      [
        "automation-status",
        "automation-tasks",
        "source-health",
        "automation-deliveries",
      ].forEach((key) => client.invalidateQueries({ queryKey: [key] }));
      setNotice(
        "Operational change recorded. Queued work still requires a running worker.",
      );
    },
  });
  return (
    <section className="panel form-panel">
      <h2>Operator automation controls</h2>
      {status.isPending ? (
        <Loading />
      ) : status.error ? (
        <ErrorBox error={status.error} />
      ) : (
        <>
          <p>{status.data!.health_note}</p>
          <p>
            Last completed worker tick:{" "}
            {status.data!.last_completed_tick_at
              ? new Date(status.data!.last_completed_tick_at).toLocaleString()
              : "Not recorded"}{" "}
            · Downstream automation{" "}
            {status.data!.enabled ? "enabled" : "paused"} · Email{" "}
            {status.data!.email_available ? "configured" : "unavailable"}.
          </p>
          <p>
            {status.data!.pending_reminders} pending reminders ·{" "}
            {status.data!.due_reminders} due ·{" "}
            {status.data!.retrying_source_runs} source retries pending.
          </p>
          <h3>Persisted task states</h3>
          <pre className="automation-json">
            {JSON.stringify(status.data!.task_counts, null, 2)}
          </pre>
          <h3>Persisted outbox states</h3>
          <pre className="automation-json">
            {JSON.stringify(status.data!.outbox_counts, null, 2)}
          </pre>
        </>
      )}
      {sources
        .filter(
          (source) => source.enabled && source.adapter_key === "himalayas",
        )
        .map((source) => (
          <form
            className="automation-schedule"
            key={`${source.id}-${source.schedule_hours}`}
            onSubmit={(e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              mutation.mutate({
                path: `/automation/sources/${source.id}/schedule`,
                body: {
                  enabled: f.has("enabled"),
                  interval_hours: Number(f.get("hours")),
                  page_limit: Number(f.get("pages")),
                },
              });
            }}
          >
            <h3>{source.name} schedule</h3>
            <label>
              <input
                name="enabled"
                type="checkbox"
                defaultChecked={!!source.schedule_hours}
              />{" "}
              Enable scheduled synchronization
            </label>
            <div className="form-grid">
              <Field
                label={`Interval hours for ${source.name}`}
                hint="Minimum 24 hours; the source feed is refreshed daily."
              >
                <input
                  name="hours"
                  type="number"
                  min={24}
                  max={720}
                  defaultValue={source.schedule_hours || 24}
                  required
                />
              </Field>
              <Field label={`Page limit for ${source.name}`}>
                <input
                  name="pages"
                  type="number"
                  min={1}
                  max={25}
                  defaultValue={source.page_limit || 2}
                  required
                />
              </Field>
            </div>
            <button className="secondary" disabled={mutation.isPending}>
              Save {source.name} schedule
            </button>
          </form>
        ))}
      {notice && <p role="status">{notice}</p>}
      {mutation.error && <ErrorBox error={mutation.error} />}
      <h3>Background execution history</h3>
      {tasks.isPending ? (
        <Loading />
      ) : tasks.error ? (
        <ErrorBox error={tasks.error} />
      ) : (
        <>
          {tasks.data!.items.map((task) => (
            <article key={task.id} className="automation-task">
              <strong>
                {label(task.kind)} · {label(task.status)}
              </strong>
              <p>
                {task.attempts} execution attempt(s), {task.retries}{" "}
                recovery/retry failure(s) · Due{" "}
                {new Date(task.due_at).toLocaleString()}
              </p>
              {task.error_code && <p>{label(task.error_code)}</p>}
              <pre className="automation-json">
                {JSON.stringify(task.outcome, null, 2)}
              </pre>
              {task.status === "failed" &&
                ["worker_interrupted", "database_unavailable"].includes(
                  task.error_code || "",
                ) && (
                  <button
                    className="secondary"
                    onClick={() =>
                      mutation.mutate({
                        path: `/automation/tasks/${task.id}/retry`,
                        body: {},
                      })
                    }
                  >
                    Retry safe failed task
                  </button>
                )}
            </article>
          ))}
          {!tasks.data!.items.length && <p>No persisted background tasks.</p>}
          <Pagination page={page} total={tasks.data!.total} change={setPage} />
        </>
      )}
      <h3>Delivery history and uncertain outcomes</h3>
      {deliveries.isPending ? (
        <Loading />
      ) : deliveries.error ? (
        <ErrorBox error={deliveries.error} />
      ) : (
        <>
          {deliveries.data!.items.map((d) => (
            <article className="automation-task" key={d.id}>
              <strong>
                {label(d.channel)} · {label(d.status)}
              </strong>
              <p>
                {d.attempts} attempt(s) · {d.error_code && label(d.error_code)}
              </p>
              <details>
                <summary>Delivery attempts</summary>
                <pre className="automation-json">
                  {JSON.stringify(d.history, null, 2)}
                </pre>
              </details>
              {d.status === "uncertain" && (
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    const f = new FormData(e.currentTarget);
                    mutation.mutate({
                      path: `/automation/deliveries/${d.id}/reconcile`,
                      body: {
                        decision: f.get("decision"),
                        evidence: f.get("evidence"),
                      },
                    });
                  }}
                >
                  <p>
                    Check provider records before recording the outcome.
                    Reconciliation does not resend.
                  </p>
                  <Field label="Verified outcome">
                    <select name="decision">
                      <option value="delivered">Delivered</option>
                      <option value="failed">Failed</option>
                    </select>
                  </Field>
                  <Field
                    label="Provider verification evidence"
                    hint="Do not include credentials or private message content."
                  >
                    <input
                      name="evidence"
                      required
                      minLength={10}
                      maxLength={200}
                    />
                  </Field>
                  <button className="secondary" disabled={mutation.isPending}>
                    Record verified outcome
                  </button>
                </form>
              )}
            </article>
          ))}
          <Pagination
            page={deliveryPage}
            total={deliveries.data!.total}
            change={setDeliveryPage}
          />
        </>
      )}
    </section>
  );
}
