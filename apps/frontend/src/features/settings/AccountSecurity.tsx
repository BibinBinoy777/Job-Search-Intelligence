import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../services/api-client";
import { ErrorBox, Field, Loading, PageHeading } from "../../components/ui";
export default function AccountSecurity() {
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState("");
  const [review, setReview] = useState(false);
  const [busy, setBusy] = useState(false);
  const sessions = useQuery({
    queryKey: ["account-sessions"],
    queryFn: () =>
      api<{ sessions: { id: string; expires_at: string }[] }>(
        "/account/sessions",
      ),
  });
  async function action(path: string, body?: unknown) {
    setBusy(true);
    setError(null);
    try {
      const result = await api<{ status: string }>(
        path,
        path.endsWith("sessions") ? "DELETE" : "POST",
        body,
      );
      setNotice(
        result.status === "deletion_pending"
          ? "Account access is disabled while private file cleanup is pending. An operator can retry cleanup."
          : "Your change was saved. If sessions were revoked, sign in again to continue.",
      );
      if (result.status === "deleted") window.location.assign("/");
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeading
        eyebrow="YOUR ACCOUNT"
        title="Security and privacy."
        description="Manage your sessions, export your own data, or explicitly delete your account."
      />
      <section className="panel form-panel">
        <h2>Active sessions</h2>
        {sessions.isPending ? (
          <Loading />
        ) : sessions.error ? (
          <ErrorBox error={sessions.error} />
        ) : (
          sessions.data!.sessions.map((s) => (
            <p key={s.id}>
              Session expires {new Date(s.expires_at).toLocaleString()}
            </p>
          ))
        )}
        <button
          className="secondary"
          disabled={busy}
          onClick={() => action("/account/sessions")}
        >
          Revoke all sessions and sign out
        </button>
        <h2>Change password</h2>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            action("/account/password", {
              current_password: f.get("current"),
              new_password: f.get("next"),
            });
          }}
        >
          <Field label="Current password">
            <input
              type="password"
              name="current"
              required
              autoComplete="current-password"
            />
          </Field>
          <Field label="New password">
            <input
              type="password"
              name="next"
              required
              minLength={12}
              maxLength={128}
              autoComplete="new-password"
            />
          </Field>
          <button className="primary" disabled={busy}>
            Change password and revoke all sessions
          </button>
        </form>
        <h2>Private data export</h2>
        <p>
          Your export contains your recorded candidate information and stored
          resume files. Keep it private. Shared jobs and other accounts are
          excluded.
        </p>
        <a href="/api/v1/account/export" className="secondary">
          Download my account ZIP
        </a>
        <h2>Delete account</h2>
        <p>
          Deletion removes your profile, applications/history, matching results,
          saves, alerts, notifications, resume originals and extraction records.
          Shared vacancies remain. Backups follow their separate retention
          policy. File cleanup failures leave the account inaccessible and
          pending operator cleanup.
        </p>
        <button className="secondary" onClick={() => setReview(!review)}>
          Review account deletion
        </button>
        {review && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              action("/account/deletion/confirm", {
                password: f.get("password"),
                confirmation: f.get("confirmation"),
              });
            }}
          >
            <Field label="Password to confirm deletion">
              <input
                type="password"
                name="password"
                required
                autoComplete="current-password"
              />
            </Field>
            <Field label="Type DELETE MY ACCOUNT">
              <input name="confirmation" required pattern="DELETE MY ACCOUNT" />
            </Field>
            <button className="primary" disabled={busy}>
              Permanently delete my account
            </button>
          </form>
        )}
        {notice && <p role="status">{notice}</p>}
        {error !== null && <ErrorBox error={error} />}
      </section>
    </>
  );
}
export function RecoveryPage() {
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState("");
  return (
    <section className="panel form-panel">
      <h2>Account recovery</h2>
      <p>
        Recovery email delivery is not configured. A local operator can issue a
        private, single-use recovery credential in development mode. It is never
        displayed by the API or written to logs.
      </p>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          try {
            await api("/account/recovery/confirm", "POST", {
              token: f.get("token"),
              password: f.get("password"),
            });
            setNotice(
              "Password changed and sessions revoked. Sign in with your new password.",
            );
          } catch (err) {
            setError(err);
          }
        }}
      >
        <Field label="Recovery credential">
          <input name="token" type="password" required autoComplete="off" />
        </Field>
        <Field label="New recovery password">
          <input
            name="password"
            type="password"
            minLength={12}
            maxLength={128}
            required
            autoComplete="new-password"
          />
        </Field>
        <button className="primary">Recover account</button>
      </form>
      {notice && <p role="status">{notice}</p>}
      {error !== null && <ErrorBox error={error} />}
    </section>
  );
}
