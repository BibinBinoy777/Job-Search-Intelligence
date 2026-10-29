import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../../services/api-client";
import {
  Empty,
  ErrorBox,
  Field,
  Loading,
  PageHeading,
  Pagination,
} from "../../components/ui";
import type { Page } from "../../types";
import type { Notification, Subscription } from "./types";
import { NotificationCard } from "./Notifications";

export default function AlertsPage() {
  const client = useQueryClient();
  const [params] = useSearchParams();
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<Subscription | null>(null);
  const [criteria, setCriteria] = useState(params.get("criteria") || "{}");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [activity, setActivity] = useState<string | null>(null);
  const [copied, setCopied] = useState("");
  const q = useQuery({
    queryKey: ["alerts", page],
    queryFn: () => api<Page<Subscription>>(`/alerts?page=${page}&page_size=20`),
  });
  const saved = useQuery({
    queryKey: ["saved-searches"],
    queryFn: () =>
      api<
        Page<{ id: string; name: string; criteria: Record<string, unknown> }>
      >("/saved-searches?page_size=50"),
  });
  const log = useQuery({
    queryKey: ["alert-activity", activity],
    queryFn: () => api<Page<Notification>>(`/alerts/${activity}/activity`),
    enabled: !!activity,
  });
  useEffect(() => {
    const id = params.get("saved_search");
    const source = saved.data?.items.find((s) => s.id === id);
    if (!editing && source && copied !== id) {
      setCriteria(JSON.stringify(source.criteria, null, 2));
      setCopied(id!);
    }
  }, [saved.data, params, copied, editing]);
  let parsed: Record<string, unknown> = {};
  try {
    parsed = JSON.parse(criteria);
  } catch {
    /* Server and submit validation remain authoritative. */
  }
  function setField(key: string, value: string, numeric = false) {
    try {
      const obj = JSON.parse(criteria);
      if (!value) delete obj[key];
      else obj[key] = numeric ? Number(value) : value;
      setCriteria(JSON.stringify(obj, null, 2));
      setError(null);
    } catch {
      setError(
        new Error(
          "Correct the criteria JSON before using the basic filter fields.",
        ),
      );
    }
  }
  const mutation = useMutation({
    mutationFn: ({
      path = "",
      method = "POST",
      body,
    }: {
      path?: string;
      method?: string;
      body?: unknown;
    }) => api<Subscription>(`/alerts${path}`, method, body),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["alerts"] });
      client.invalidateQueries({ queryKey: ["alert-activity"] });
      setEditing(null);
      setDeleting(null);
      setNotice(
        "Alert change saved. Only future qualifying job events will be considered; saving does not mean a notification was delivered.",
      );
    },
  });
  function bodyOf(s: Subscription) {
    return {
      name: s.name,
      criteria: s.criteria,
      saved_search_id: s.saved_search_id,
      enabled: s.enabled,
      include_updates: s.include_updates,
      email: s.email,
      expected_revision: s.revision,
    };
  }
  if (q.error instanceof ApiError && q.error.status === 404)
    return (
      <Empty
        title="Create your profile first"
        action={<Link to="/profile">Create profile</Link>}
      >
        Alert subscriptions use your existing candidate profile.
      </Empty>
    );
  return (
    <>
      <PageHeading
        eyebrow="EXPLICIT SUBSCRIPTIONS, CONSERVATIVE DELIVERY"
        title="Job alerts."
        description="Saving a search does not subscribe you. Choose what future verified job events you want to hear about."
      />
      <p>
        <Link to="/notifications">
          Enable job alerts and delivery preferences
        </Link>
        . Email needs provider configuration and explicit global and
        subscription opt-in. Score/coverage filters require current assessments
        at evaluation; missing or stale scores are skipped, with no implicit
        calculation.
      </p>
      <section className="panel form-panel">
        <h2>
          {editing ? `Edit ${editing.name}` : "Create a future-event alert"}
        </h2>
        {!editing && (
          <Field label="Copy an existing saved search">
            <select
              value={copied}
              onChange={(e) => {
                const item = saved.data?.items.find(
                  (s) => s.id === e.target.value,
                );
                setCopied(e.target.value);
                if (item) setCriteria(JSON.stringify(item.criteria, null, 2));
              }}
            >
              <option value="">Use current criteria below</option>
              {saved.data?.items.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </Field>
        )}
        <form
          key={editing?.id || "new"}
          onSubmit={(e) => {
            e.preventDefault();
            setError(null);
            try {
              const f = new FormData(e.currentTarget);
              const filters = JSON.parse(criteria);
              mutation.mutate({
                path: editing ? `/${editing.id}` : "",
                method: editing ? "PUT" : "POST",
                body: {
                  name: f.get("name"),
                  criteria: filters,
                  ...(copied && !editing ? { saved_search_id: copied } : {}),
                  enabled: f.has("enabled"),
                  include_updates: f.has("include_updates"),
                  email: f.has("email"),
                  ...(editing ? { expected_revision: editing.revision } : {}),
                },
              });
            } catch {
              setError(new Error("Criteria must be a valid JSON object."));
            }
          }}
        >
          <Field label="Alert name">
            <input
              name="name"
              defaultValue={editing?.name || ""}
              maxLength={100}
              required
            />
          </Field>
          <div className="form-grid">
            <Field label="Alert keywords">
              <input
                value={String(parsed.q || "")}
                onChange={(e) => setField("q", e.target.value)}
                maxLength={200}
              />
            </Field>
            <Field label="Alert location">
              <input
                value={String(parsed.location || "")}
                onChange={(e) => setField("location", e.target.value)}
                maxLength={250}
              />
            </Field>
            <Field label="Alert work arrangement">
              <select
                value={String(parsed.work_arrangement || "")}
                onChange={(e) => setField("work_arrangement", e.target.value)}
              >
                <option value="">Any specified arrangement</option>
                <option value="remote">Remote</option>
                <option value="hybrid">Hybrid</option>
                <option value="on_site">On site</option>
              </select>
            </Field>
            <Field
              label="Minimum current match score"
              hint="Optional 0–100 relevance threshold, not hiring probability."
            >
              <input
                type="number"
                min={0}
                max={100}
                value={
                  parsed.minimum_score == null
                    ? ""
                    : String(parsed.minimum_score)
                }
                onChange={(e) =>
                  setField("minimum_score", e.target.value, true)
                }
              />
            </Field>
            <Field label="Minimum required-skill coverage">
              <input
                type="number"
                min={0}
                max={1}
                step={0.01}
                value={
                  parsed.required_coverage == null
                    ? ""
                    : String(parsed.required_coverage)
                }
                onChange={(e) =>
                  setField("required_coverage", e.target.value, true)
                }
              />
            </Field>
          </div>
          <details>
            <summary>Review or edit all copied search criteria</summary>
            <Field
              label="Alert search criteria JSON"
              hint="Uses the existing validated search schema; historical/stale/unknown availability filters are rejected."
            >
              <textarea
                value={criteria}
                onChange={(e) => setCriteria(e.target.value)}
                rows={8}
              />
            </Field>
          </details>
          <div className="automation-checks">
            <label>
              <input
                name="enabled"
                type="checkbox"
                defaultChecked={editing?.enabled ?? true}
              />
              Enabled
            </label>
            <label>
              <input
                name="include_updates"
                type="checkbox"
                defaultChecked={editing?.include_updates ?? false}
              />
              Also alert on material content updates
            </label>
            <label>
              <input
                name="email"
                type="checkbox"
                defaultChecked={editing?.email ?? false}
              />
              Optional email for this subscription
            </label>
          </div>
          <p>
            Initial policy: future events only. No existing-job backfill.
            Immediate delivery means the next worker pass. Editing or resuming
            starts a new future-only window.
          </p>
          <button className="primary" disabled={mutation.isPending}>
            {editing ? "Save alert changes" : "Create alert subscription"}
          </button>
          {editing && (
            <button
              className="text-button"
              type="button"
              onClick={() => {
                setEditing(null);
                setCriteria("{}");
              }}
            >
              Cancel edit
            </button>
          )}
        </form>
        {error !== null && <ErrorBox error={error} />}
      </section>
      {notice && <p role="status">{notice}</p>}
      {mutation.error && <ErrorBox error={mutation.error} />}
      <h2>Your subscriptions</h2>
      {q.isPending ? (
        <Loading />
      ) : q.error ? (
        <ErrorBox error={q.error} />
      ) : q.data!.items.length ? (
        <>
          {q.data!.items.map((s) => (
            <article className="panel form-panel" key={s.id}>
              <h3>{s.name}</h3>
              <p>
                {s.enabled ? "Enabled" : "Paused"} · New listings
                {s.include_updates ? " and material updates" : " only"} · Future
                events after {new Date(s.starts_after).toLocaleString()}
              </p>
              <pre className="automation-json">
                {JSON.stringify(s.criteria, null, 2)}
              </pre>
              <div className="automation-actions">
                <button
                  className="secondary"
                  onClick={() =>
                    mutation.mutate({
                      path: `/${s.id}`,
                      method: "PUT",
                      body: { ...bodyOf(s), enabled: !s.enabled },
                    })
                  }
                >
                  {s.enabled ? "Pause" : "Resume"} {s.name}
                </button>
                <button
                  className="text-button"
                  onClick={() => {
                    setEditing(s);
                    setCriteria(JSON.stringify(s.criteria, null, 2));
                    setCopied("");
                  }}
                >
                  Edit {s.name}
                </button>
                <button
                  className="text-button"
                  onClick={() => setActivity(s.id)}
                >
                  Recent activity for {s.name}
                </button>
                <button
                  className="text-button"
                  onClick={() => setDeleting(s.id)}
                >
                  Delete {s.name}
                </button>
                {deleting === s.id && (
                  <button
                    className="secondary"
                    onClick={() =>
                      mutation.mutate({ path: `/${s.id}`, method: "DELETE" })
                    }
                  >
                    Confirm delete subscription
                  </button>
                )}
              </div>
            </article>
          ))}
          <Pagination page={page} total={q.data!.total} change={setPage} />
        </>
      ) : (
        <Empty title="No alert subscriptions">
          A saved search remains a definition until you explicitly create an
          alert.
        </Empty>
      )}
      {activity && (
        <section>
          <h2>Recent alert activity</h2>
          {log.isPending ? (
            <Loading />
          ) : log.error ? (
            <ErrorBox error={log.error} />
          ) : log.data!.items.length ? (
            log.data!.items.map((n) => <NotificationCard key={n.id} item={n} />)
          ) : (
            <p>No notifications have been created for this subscription.</p>
          )}
        </section>
      )}
    </>
  );
}
