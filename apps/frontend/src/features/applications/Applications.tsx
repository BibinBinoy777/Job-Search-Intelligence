import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowUpRight, ChevronDown, Plus } from "lucide-react";
import { api, ApiError } from "../../services/api-client";
import {
  statuses,
  type Application,
  type AppEvent,
  type Job,
  type Page,
} from "../../types";
import {
  dateLabel,
  Empty,
  ErrorBox,
  Field,
  label,
  Loading,
  PageHeading,
  Pagination,
} from "../../components/ui";

export default function ApplicationsPage() {
  const [page, setPage] = useState(1);
  const [params, setParams] = useSearchParams();
  const [adding, setAdding] = useState(false);
  const q = useQuery({
    queryKey: ["applications", page],
    queryFn: () =>
      api<Page<Application>>(`/applications?page=${page}&page_size=12`),
  });
  const missingProfile = q.error instanceof ApiError && q.error.status === 404;
  return (
    <>
      <PageHeading
        eyebrow="YOUR NEXT STEPS, IN PERSPECTIVE"
        title="A little progress, every day."
        description="Keep track of your applications, notes, and the milestones that matter."
        action={
          <button className="primary" onClick={() => setAdding(!adding)}>
            <Plus size={17} />
            Track a job
          </button>
        }
      />
      <div className="status-legend">
        {statuses.map((s) => (
          <span key={s}>
            <i className={`status-mark ${s}`} />
            {label(s)}
          </span>
        ))}
      </div>
      {adding && <CreateApplication close={() => setAdding(false)} />}
      {q.isPending ? (
        <Loading />
      ) : q.error && !missingProfile ? (
        <ErrorBox error={q.error} retry={() => q.refetch()} />
      ) : missingProfile || !q.data?.items.length ? (
        <section className="panel">
          <Empty
            title={
              missingProfile
                ? "Create your profile first"
                : "Your journey is yours to shape"
            }
            action={
              <Link
                to={missingProfile ? "/profile" : "/jobs"}
                className="secondary"
              >
                {missingProfile ? "Create profile" : "Discover jobs"}
              </Link>
            }
          >
            {missingProfile
              ? "Applications are owned by your candidate profile."
              : "Track an opportunity to keep its status, notes, and follow-up dates together."}
          </Empty>
        </section>
      ) : (
        <section className="panel application-list">
          {q.data.items.map((a) => (
            <ApplicationRow
              key={a.id}
              application={a}
              open={params.get("open") === a.id}
              toggle={() =>
                setParams(params.get("open") === a.id ? {} : { open: a.id })
              }
            />
          ))}
        </section>
      )}
      {params.get("open") &&
        q.data &&
        !q.data.items.some((a) => a.id === params.get("open")) && (
          <LinkedApplication id={params.get("open")!} />
        )}
      {q.data && (
        <Pagination page={page} total={q.data.total} change={setPage} />
      )}
    </>
  );
}

function LinkedApplication({ id }: { id: string }) {
  const q = useQuery({
    queryKey: ["application", id],
    queryFn: () => api<Application>(`/applications/${id}`),
  });
  return q.isPending ? (
    <Loading />
  ) : q.error ? (
    <ErrorBox error={q.error} />
  ) : (
    <ApplicationRow application={q.data!} open={true} toggle={() => {}} />
  );
}

function CreateApplication({ close }: { close: () => void }) {
  const client = useQueryClient();
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const jobs = useQuery({
    queryKey: ["jobs", "picker", search, page],
    queryFn: () =>
      api<Page<Job>>(
        `/jobs?page_size=12&page=${page}&q=${encodeURIComponent(search)}`,
      ),
  });
  const m = useMutation({
    mutationFn: (data: unknown) => api("/applications", "POST", data),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["applications"] });
      client.invalidateQueries({ queryKey: ["overview"] });
      close();
    },
  });
  function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    m.mutate({
      job_id: f.get("job_id"),
      status: f.get("status"),
      notes: f.get("notes") || null,
    });
  }
  return (
    <section className="panel form-panel">
      <h2>Add to your application tracker</h2>
      <Field label="Find a persisted job">
        <input
          type="search"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
          placeholder="Search title or employer"
        />
      </Field>
      {jobs.isPending ? (
        <Loading />
      ) : jobs.error ? (
        <ErrorBox error={jobs.error} />
      ) : jobs.data?.items.length ? (
        <>
          <form onSubmit={submit}>
            <div className="form-grid">
              <Field label="Opportunity">
                <select name="job_id" required>
                  {jobs.data.items.map((j) => (
                    <option key={j.id} value={j.id}>
                      {j.title} · {j.employer}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Initial status">
                <select name="status">
                  {statuses.map((s) => (
                    <option key={s} value={s}>
                      {label(s)}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
            <Field label="Notes">
              <textarea name="notes" maxLength={10000} />
            </Field>
            {m.error && <ErrorBox error={m.error} />}
            <div className="form-actions">
              <button className="secondary" type="button" onClick={close}>
                Cancel
              </button>
              <button className="primary" disabled={m.isPending}>
                Add application
              </button>
            </div>
          </form>
          <Pagination page={page} total={jobs.data.total} change={setPage} />
        </>
      ) : (
        <Empty title="No persisted jobs found">
          Check data sources for actual collection status, or broaden your
          search. An operator can also import an actual supplied job record.
        </Empty>
      )}
    </section>
  );
}

function ApplicationRow({
  application: a,
  open,
  toggle,
}: {
  application: Application;
  open: boolean;
  toggle: () => void;
}) {
  return (
    <article className="application-row">
      <button
        className="application-summary"
        onClick={toggle}
        aria-expanded={open}
      >
        <span className="employer-icon">{a.job.employer[0]}</span>
        <span className="application-title">
          <strong>{a.job.title}</strong>
          <small>
            {a.job.employer} · Updated {dateLabel(a.updated_at)}
          </small>
        </span>
        <span className={`badge ${a.status}`}>{label(a.status)}</span>
        <ChevronDown size={18} className={open ? "rotated" : ""} />
      </button>
      {open && <ApplicationEditor application={a} />}
    </article>
  );
}

function ApplicationEditor({ application: a }: { application: Application }) {
  const client = useQueryClient();
  const [success, setSuccess] = useState(false);
  const [eventPage, setEventPage] = useState(1);
  const history = useQuery({
    queryKey: ["events", a.id, eventPage],
    queryFn: () =>
      api<Page<AppEvent>>(
        `/applications/${a.id}/events?page=${eventPage}&page_size=12`,
      ),
  });
  const mutation = useMutation({
    mutationFn: (value: unknown) =>
      api(`/applications/${a.id}`, "PATCH", value),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["applications"] });
      client.invalidateQueries({ queryKey: ["events", a.id] });
      client.invalidateQueries({ queryKey: ["overview"] });
      setSuccess(true);
    },
    onError: () => client.invalidateQueries({ queryKey: ["applications"] }),
  });
  function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSuccess(false);
    const f = new FormData(e.currentTarget);
    const data: Record<string, unknown> = {
      expected_version: a.version,
      status: f.get("status"),
      notes: f.get("notes") || null,
      applied_on: f.get("applied_on") || null,
      follow_up_on: f.get("follow_up_on") || null,
    };
    if (f.get("correction_reason"))
      data.correction_reason = f.get("correction_reason");
    mutation.mutate(data);
  }
  return (
    <div className="application-editor">
      <form onSubmit={submit} key={a.version}>
        <div className="form-grid">
          <Field label="Application status">
            <select name="status" defaultValue={a.status}>
              {statuses.map((s) => (
                <option key={s} value={s}>
                  {label(s)}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Application date">
            <input
              name="applied_on"
              type="date"
              defaultValue={a.applied_on || ""}
            />
          </Field>
          <Field label="Follow-up date">
            <input
              name="follow_up_on"
              type="date"
              defaultValue={a.follow_up_on || ""}
            />
          </Field>
        </div>
        <Field label="Application notes">
          <textarea
            name="notes"
            rows={3}
            maxLength={10000}
            defaultValue={a.notes || ""}
          />
        </Field>
        {["offer", "rejected", "withdrawn"].includes(a.status) && (
          <Field
            label="Correction reason"
            hint="Required when changing a recorded outcome."
          >
            <input name="correction_reason" minLength={3} maxLength={500} />
          </Field>
        )}
        {mutation.error && <ErrorBox error={mutation.error} />}
        <div className="form-actions">
          <Link to={`/jobs/${a.job.id}`} className="text-button">
            View job
            <ArrowUpRight size={15} />
          </Link>
          <Link to={`/reminders?application=${a.id}`} className="text-button">
            Schedule reminder
          </Link>
          {success && (
            <span className="success" role="status">
              Application updated.
            </span>
          )}
          <button className="primary" disabled={mutation.isPending}>
            Save application
          </button>
        </div>
      </form>
      <div className="application-history">
        <h3>Status history</h3>
        {history.isPending ? (
          <Loading />
        ) : history.error ? (
          <ErrorBox error={history.error} retry={() => history.refetch()} />
        ) : (
          <>
            <ol className="timeline">
              {history.data!.items.map((e) => (
                <li key={e.id}>
                  <span />
                  <div>
                    <strong>
                      {e.from_status
                        ? `${label(e.from_status)} → ${label(e.to_status)}`
                        : `Added as ${label(e.to_status).toLowerCase()}`}
                    </strong>
                    <small>{new Date(e.created_at).toLocaleString()}</small>
                    {e.reason && <p>{e.reason}</p>}
                  </div>
                </li>
              ))}
            </ol>
            <Pagination
              page={eventPage}
              total={history.data!.total}
              change={setEventPage}
            />
          </>
        )}
      </div>
    </div>
  );
}
