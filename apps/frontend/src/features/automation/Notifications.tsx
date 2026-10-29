import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../../services/api-client";
import {
  Empty,
  ErrorBox,
  Field,
  Loading,
  PageHeading,
  Pagination,
  label,
} from "../../components/ui";
import type { Page } from "../../types";
import type { Capabilities, Notification, Preferences } from "./types";

export function NotificationIndicator() {
  const q = useQuery({
    queryKey: ["notification-indicator"],
    queryFn: () => api<{ unread_count: number }>("/notifications?page_size=1"),
    refetchInterval: 60000,
  });
  return (
    <Link to="/notifications" className="notification-indicator">
      Notifications
      {q.data
        ? ` (${q.data.unread_count} unread)`
        : q.error
          ? " (unavailable)"
          : ""}
    </Link>
  );
}
export function NotificationPreferences() {
  const client = useQueryClient();
  const [notice, setNotice] = useState("");
  const q = useQuery({
    queryKey: ["notification-preferences"],
    queryFn: () => api<Capabilities>("/notifications/preferences"),
  });
  const save = useMutation({
    mutationFn: (data: Preferences) =>
      api<Preferences>("/notifications/preferences", "PUT", data),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["notification-preferences"] });
      setNotice(
        "Notification preferences saved. Pending deliveries will check these preferences again.",
      );
    },
  });
  return (
    <section className="panel form-panel">
      <h2>Delivery preferences</h2>
      {q.isPending ? (
        <Loading />
      ) : q.error ? (
        <ErrorBox error={q.error} />
      ) : (
        <>
          <p>
            Job alerts require explicit opt-in. Manual application reminders use
            their own enablement. Email is{" "}
            {q.data!.email_available
              ? "configured; explicit opt-in is required"
              : "unavailable because no provider is configured"}
            . A worker must run to evaluate and deliver notifications.
          </p>
          <form
            key={JSON.stringify(q.data!.preferences)}
            onSubmit={(e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              save.mutate({
                job_alerts: f.has("job_alerts"),
                reminders: f.has("reminders"),
                in_app: f.has("in_app"),
                email: f.has("email"),
                timezone: String(f.get("timezone")),
              });
            }}
          >
            <div className="automation-checks">
              {[
                ["job_alerts", "Enable job alerts"],
                ["reminders", "Enable application reminders"],
                ["in_app", "Deliver in-app notifications"],
                ["email", "Deliver optional email"],
              ].map(([key, text]) => (
                <label key={key}>
                  <input
                    type="checkbox"
                    name={key}
                    defaultChecked={
                      q.data!.preferences[key as keyof Preferences] === true
                    }
                    disabled={key === "email" && !q.data!.email_available}
                  />
                  {text}
                </label>
              ))}
            </div>
            <Field
              label="Preferred timezone"
              hint="IANA name, for example Asia/Kolkata or America/New_York. Reminder forms preserve an explicit timezone."
            >
              <input
                name="timezone"
                defaultValue={q.data!.preferences.timezone}
                maxLength={100}
                required
              />
            </Field>
            <p className="small muted">
              Immediate means the next worker pass, not guaranteed instant
              delivery. Digests and quiet hours are not implemented. Disabling a
              channel suppresses pending deliveries; already delivered messages
              cannot be recalled.
            </p>
            <button className="primary" disabled={save.isPending}>
              Save notification preferences
            </button>
          </form>
        </>
      )}
      {notice && <p role="status">{notice}</p>}
      {save.error && <ErrorBox error={save.error} />}
    </section>
  );
}
export function NotificationCard({
  item,
  onRead,
}: {
  item: Notification;
  onRead?: (item: Notification) => void;
}) {
  return (
    <article className="panel form-panel notification-card">
      <div className="section-heading">
        <h3>{item.title}</h3>
        <span className="badge">
          {item.in_app_status === "delivered"
            ? item.read_at
              ? "Read"
              : "Unread"
            : label(item.in_app_status)}
        </span>
      </div>
      <p>{item.message}</p>
      <p className="small muted">
        {label(item.category)} · {new Date(item.created_at).toLocaleString()}.
        Recorded event; the related listing or application may have changed.
      </p>
      <Link to={item.href}>
        Open related{" "}
        {item.application_id
          ? "application"
          : item.job_id
            ? "job"
            : "automation history"}
      </Link>
      {onRead && (
        <button className="text-button" onClick={() => onRead(item)}>
          {item.read_at ? "Mark unread" : "Mark read"}
        </button>
      )}
      <details>
        <summary>Delivery status</summary>
        <ul>
          {item.deliveries.map((d) => (
            <li key={d.id}>
              {label(d.channel)}: {label(d.status)} · {d.attempts} attempt(s)
              {d.error_code ? ` · ${label(d.error_code)}` : ""}
            </li>
          ))}
        </ul>
        {item.deliveries.length === 0 && (
          <p>No channel was queued under the recorded preferences.</p>
        )}
      </details>
    </article>
  );
}
export default function NotificationsPage() {
  const client = useQueryClient();
  const [page, setPage] = useState(1);
  const [history, setHistory] = useState(false);
  const q = useQuery({
    queryKey: ["notifications", page, history],
    queryFn: () =>
      api<Page<Notification> & { unread_count: number }>(
        `/notifications?page=${page}&page_size=20&include_history=${history}`,
      ),
    refetchOnMount: "always",
    refetchInterval: 60000,
  });
  const read = useMutation({
    mutationFn: (item: Notification) =>
      api(`/notifications/${item.id}/read`, "PATCH", { read: !item.read_at }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["notifications"] });
      client.invalidateQueries({ queryKey: ["notification-indicator"] });
    },
  });
  return (
    <>
      <PageHeading
        eyebrow="ACTUAL EVENTS, OWNED BY YOU"
        title="Your notifications."
        description="Job alerts and application reminders, with their real delivery state."
      />
      <NotificationPreferences />
      <div className="section-heading">
        <h2>{q.data?.unread_count ?? "—"} unread delivered notifications</h2>
        <label>
          <input
            type="checkbox"
            checked={history}
            onChange={(e) => {
              setHistory(e.target.checked);
              setPage(1);
            }}
          />{" "}
          Include pending and suppressed delivery history
        </label>
      </div>
      {q.isPending ? (
        <Loading />
      ) : q.error ? (
        <ErrorBox error={q.error} retry={() => q.refetch()} />
      ) : q.data!.items.length ? (
        <>
          {q.data!.items.map((n) => (
            <NotificationCard
              key={n.id}
              item={n}
              onRead={(item) => read.mutate(item)}
            />
          ))}
          <Pagination page={page} total={q.data!.total} change={setPage} />
        </>
      ) : (
        <Empty title="No notifications in this view">
          No delivery has been invented. Enable your preferences, create a
          future-event alert or schedule an application reminder, and keep the
          worker running.
        </Empty>
      )}
      {read.error && <ErrorBox error={read.error} />}
      <p>
        <Link to="/alerts">Manage job-alert subscriptions</Link> ·{" "}
        <Link to="/reminders">Manage application reminders</Link>
      </p>
    </>
  );
}
