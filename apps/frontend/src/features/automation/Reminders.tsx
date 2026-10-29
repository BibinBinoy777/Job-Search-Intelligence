import { useState } from "react";
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
  label,
} from "../../components/ui";
import type { Application, Page } from "../../types";
import type { Capabilities, Reminder } from "./types";

function wallTime(iso: string, zone: string) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: zone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(iso));
  const value = (key: string) => parts.find((p) => p.type === key)?.value;
  return `${value("year")}-${value("month")}-${value("day")}T${value("hour")}:${value("minute")}`;
}
export default function RemindersPage() {
  const client = useQueryClient();
  const [params] = useSearchParams();
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<Reminder | null>(null);
  const [notice, setNotice] = useState("");
  const q = useQuery({
    queryKey: ["reminders", page],
    queryFn: () => api<Page<Reminder>>(`/reminders?page=${page}&page_size=20`),
    refetchOnMount: "always",
  });
  const apps = useQuery({
    queryKey: ["reminder-applications"],
    queryFn: () => api<Page<Application>>("/applications?page_size=100"),
  });
  const caps = useQuery({
    queryKey: ["notification-preferences"],
    queryFn: () => api<Capabilities>("/notifications/preferences"),
  });
  const mutation = useMutation({
    mutationFn: ({
      path = "",
      method = "POST",
      body,
    }: {
      path?: string;
      method?: string;
      body: unknown;
    }) => api<Reminder>(`/reminders${path}`, method, body),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["reminders"] });
      setEditing(null);
      setNotice(
        "Reminder change saved. A scheduled or queued reminder is not a delivery confirmation.",
      );
    },
  });
  if (q.error instanceof ApiError && q.error.status === 404)
    return (
      <Empty
        title="Create your profile first"
        action={<Link to="/profile">Create profile</Link>}
      >
        Reminders belong to your existing applications.
      </Empty>
    );
  return (
    <>
      <PageHeading
        eyebrow="YOUR DATES, YOUR NEXT ACTION"
        title="Application reminders."
        description="Schedule an explicit follow-up, preparation task or review. No interview date or employer deadline is inferred."
      />
      <p>
        <Link to="/notifications">Manage reminder delivery preferences</Link> ·{" "}
        <Link to="/applications">Return to applications</Link>. A running worker
        is required. Withdrawn applications cancel pending reminders.
      </p>
      <section className="panel form-panel">
        <h2>{editing ? "Edit reminder" : "Schedule a reminder"}</h2>
        {caps.isPending ? (
          <Loading />
        ) : caps.error ? (
          <ErrorBox error={caps.error} />
        ) : (
          <form
            key={editing?.id || "new"}
            onSubmit={(e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              mutation.mutate({
                path: editing ? `/${editing.id}` : "",
                method: editing ? "PUT" : "POST",
                body: {
                  application_id: f.get("application_id"),
                  kind: f.get("kind"),
                  local_time: f.get("local_time"),
                  timezone: f.get("timezone"),
                  fold: f.get("fold") === "" ? null : Number(f.get("fold")),
                  note: f.get("note") || null,
                  email: f.has("email"),
                  ...(editing ? { expected_revision: editing.revision } : {}),
                },
              });
            }}
          >
            <div className="form-grid">
              <Field
                label="Application ID"
                hint="Select one of the first 100 applications, or use Schedule reminder from an application to prefill its ID."
              >
                <input
                  name="application_id"
                  list="reminder-applications"
                  defaultValue={
                    editing?.application_id || params.get("application") || ""
                  }
                  maxLength={36}
                  required
                  readOnly={!!editing}
                />
                <datalist id="reminder-applications">
                  {apps.data?.items.map((a) => (
                    <option value={a.id} key={a.id}>
                      {a.job.title} · {a.job.employer}
                    </option>
                  ))}
                </datalist>
              </Field>
              <Field label="Reminder type">
                <select name="kind" defaultValue={editing?.kind || "follow_up"}>
                  {[
                    "follow_up",
                    "interview_preparation",
                    "deadline_review",
                    "application_update",
                    "manual",
                  ].map((kind) => (
                    <option key={kind} value={kind}>
                      {label(kind)}
                    </option>
                  ))}
                </select>
              </Field>
              <Field
                label="Local date and time"
                hint="Choose the actual intended time. Past times become due on the next worker pass."
              >
                <input
                  type="datetime-local"
                  name="local_time"
                  defaultValue={
                    editing ? wallTime(editing.due_at, editing.timezone) : ""
                  }
                  required
                />
              </Field>
              <Field
                label="Reminder timezone"
                hint="IANA timezone for this wall time, e.g. Asia/Kolkata. Stored as a UTC instant with your zone retained."
              >
                <input
                  name="timezone"
                  defaultValue={
                    editing?.timezone ||
                    caps.data?.preferences.timezone ||
                    Intl.DateTimeFormat().resolvedOptions().timeZone
                  }
                  required
                  maxLength={100}
                />
              </Field>
              <Field
                label="Repeated daylight-saving time"
                hint="Only needed if the selected local time occurs twice; nonexistent local times are rejected."
              >
                <select name="fold" defaultValue="">
                  <option value="">Not ambiguous / ask me if needed</option>
                  <option value="0">First occurrence</option>
                  <option value="1">Second occurrence</option>
                </select>
              </Field>
            </div>
            <Field label="Private reminder note">
              <textarea
                name="note"
                defaultValue={editing?.note || ""}
                maxLength={500}
              />
            </Field>
            <label>
              <input
                type="checkbox"
                name="email"
                defaultChecked={editing?.email || false}
                disabled={!caps.data?.email_available}
              />{" "}
              Also request optional email
            </label>
            <p>
              <button className="primary" disabled={mutation.isPending}>
                {editing
                  ? "Save reminder changes"
                  : "Create application reminder"}
              </button>
              {editing && (
                <button
                  type="button"
                  className="text-button"
                  onClick={() => setEditing(null)}
                >
                  Cancel edit
                </button>
              )}
            </p>
          </form>
        )}
      </section>
      {notice && <p role="status">{notice}</p>}
      {mutation.error && <ErrorBox error={mutation.error} />}
      <h2>Your reminders</h2>
      {q.isPending ? (
        <Loading />
      ) : q.error ? (
        <ErrorBox error={q.error} />
      ) : q.data!.items.length ? (
        <>
          {q.data!.items.map((r) => (
            <article className="panel form-panel" key={r.id}>
              <div className="section-heading">
                <h3>{label(r.kind)}</h3>
                <span className="badge">
                  {r.status === "notified"
                    ? "Notification queued; inspect delivery"
                    : label(r.status)}
                </span>
              </div>
              <p>
                {new Date(r.due_at).toLocaleString(undefined, {
                  timeZone: r.timezone,
                  timeZoneName: "short",
                })}{" "}
                · {r.timezone}
              </p>
              {r.note && <p>{r.note}</p>}
              <Link to={`/applications?open=${r.application_id}`}>
                Open related application
              </Link>{" "}
              · <Link to="/notifications">Inspect delivery history</Link>
              {!["cancelled", "completed"].includes(r.status) && (
                <div className="automation-actions">
                  <button className="secondary" onClick={() => setEditing(r)}>
                    Edit reminder
                  </button>
                  <button
                    className="text-button"
                    onClick={() =>
                      mutation.mutate({
                        path: `/${r.id}/action`,
                        body: {
                          action: "complete",
                          expected_revision: r.revision,
                        },
                      })
                    }
                  >
                    Complete reminder
                  </button>
                  <button
                    className="text-button"
                    onClick={() =>
                      mutation.mutate({
                        path: `/${r.id}/action`,
                        body: {
                          action: "cancel",
                          expected_revision: r.revision,
                        },
                      })
                    }
                  >
                    Cancel reminder
                  </button>
                </div>
              )}
            </article>
          ))}
          <Pagination page={page} total={q.data!.total} change={setPage} />
        </>
      ) : (
        <Empty title="No application reminders">
          Existing follow-up fields do not silently generate notifications.
          Choose a date and time explicitly.
        </Empty>
      )}
    </>
  );
}
