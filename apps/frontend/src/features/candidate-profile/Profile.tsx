import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, GraduationCap, Pencil, Plus, Trash2, X } from "lucide-react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../../services/api-client";
import type { Education, Experience, Profile } from "../../types";
import {
  dateLabel,
  label,
  ErrorBox,
  Field,
  Loading,
  PageHeading,
  splitList,
} from "../../components/ui";

export default function ProfilePage() {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ["profile"],
    queryFn: () => api<Profile>("/profile"),
  });
  const [notice, setNotice] = useState("");
  const save = useMutation({
    mutationFn: (value: unknown) =>
      api<Profile>("/profile", query.data ? "PATCH" : "POST", value),
    onSuccess: (profile) => {
      client.setQueryData(["profile"], profile);
      client.invalidateQueries({ queryKey: ["overview"] });
      setNotice("Profile saved.");
    },
  });
  if (query.isPending) return <Loading />;
  if (
    query.error &&
    !(query.error instanceof ApiError && query.error.status === 404)
  )
    return <ErrorBox error={query.error} retry={() => query.refetch()} />;
  const p = query.data;
  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setNotice("");
    const form = new FormData(event.currentTarget);
    const text = (key: string) => String(form.get(key) || "").trim() || null;
    save.mutate({
      name: text("name"),
      headline: text("headline"),
      summary: text("summary"),
      qualifications: splitList(String(form.get("qualifications"))),
      certifications: splitList(String(form.get("certifications"))),
      projects: splitList(String(form.get("projects"))),
    });
  }
  return (
    <>
      <PageHeading
        eyebrow="YOUR CAREER STORY"
        title="Make it feel like you."
        description="Your experience, strengths, and ambitions. Add what you know; fill in the rest later."
      />
      <div className="profile-layout">
        <div>
          <section className="panel form-panel">
            <div className="section-heading">
              <div>
                <h2>The essentials</h2>
                <p>A little context for your next opportunity.</p>
              </div>
              <span className="badge">
                {p ? "Your profile" : "Get started"}
              </span>
            </div>
            <form onSubmit={submit} key={p?.id || "new"}>
              <div className="form-grid">
                <Field label="Full name">
                  <input
                    name="name"
                    defaultValue={p?.name || ""}
                    maxLength={150}
                    autoComplete="name"
                  />
                </Field>
                <Field label="Professional headline">
                  <input
                    name="headline"
                    placeholder="What do you do, or aspire to do?"
                    defaultValue={p?.headline || ""}
                    maxLength={240}
                  />
                </Field>
              </div>
              <Field label="Professional summary">
                <textarea
                  name="summary"
                  rows={4}
                  defaultValue={p?.summary || ""}
                  maxLength={10000}
                  placeholder="Tell your career story in your own words."
                />
              </Field>
              <Field
                label="Relevant qualifications"
                hint="Separate entries with commas."
              >
                <input
                  name="qualifications"
                  defaultValue={p?.qualifications.join(", ") || ""}
                />
              </Field>
              <Field
                label="Certifications"
                hint="Separate entries with commas."
              >
                <input
                  name="certifications"
                  defaultValue={p?.certifications.join(", ") || ""}
                />
              </Field>
              <Field
                label="Projects"
                hint="Add a project name or a short description, separated by commas."
              >
                <textarea
                  name="projects"
                  rows={2}
                  defaultValue={p?.projects.join(", ") || ""}
                />
              </Field>
              {save.error && <ErrorBox error={save.error} />}
              <div className="form-actions">
                {notice && (
                  <span className="success" role="status">
                    <Check size={16} />
                    {notice}
                  </span>
                )}
                <button className="primary" disabled={save.isPending}>
                  {save.isPending
                    ? "Saving…"
                    : p
                      ? "Save profile"
                      : "Create profile"}
                </button>
              </div>
            </form>
          </section>
          {p && (
            <>
              <Skills profile={p} />
              <History kind="experience" records={p.experience} />
              <History kind="education" records={p.education} />
            </>
          )}
        </div>
        <aside className="profile-aside">
          <div className="panel tip-card">
            <span className="stat-icon lavender">
              <GraduationCap size={24} />
            </span>
            <h3>Your story is still being written.</h3>
            <p>
              You don’t need a perfect profile to start. Add your skills,
              projects, and the experience that matters to you.
            </p>
            <hr />
            <strong>You’re in control</strong>
            <p>
              Nothing here is inferred by AI. Your profile contains only the
              information you choose to add.
            </p>
            <Link className="text-button" to="/settings">
              Set your search preferences →
            </Link>
          </div>
        </aside>
      </div>
    </>
  );
}

function Skills({ profile }: { profile: Profile }) {
  const client = useQueryClient();
  const [name, setName] = useState("");
  const mutation = useMutation({
    mutationFn: ({ id, name }: { id?: string; name?: string }) =>
      id
        ? api(`/profile/skills/${id}`, "DELETE")
        : api("/profile/skills", "POST", { name }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["profile"] });
      client.invalidateQueries({ queryKey: ["overview"] });
      setName("");
    },
  });
  return (
    <section className="panel form-panel">
      <div className="section-heading">
        <div>
          <h2>Your skills</h2>
          <p>The tools and strengths you bring to the table.</p>
        </div>
      </div>
      <div className="skill-list">
        {profile.skills.length ? (
          profile.skills.map((s) => (
            <span className="skill" key={s.id}>
              {s.name}
              <button
                aria-label={`Remove ${s.name}`}
                disabled={mutation.isPending}
                onClick={() => mutation.mutate({ id: s.id })}
              >
                <X size={13} />
              </button>
            </span>
          ))
        ) : (
          <p className="muted">No skills added yet.</p>
        )}
      </div>
      <form
        className="inline-form"
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate({ name });
        }}
      >
        <Field label="Add a skill">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            maxLength={100}
            placeholder="e.g. Python"
          />
        </Field>
        <button
          className="secondary"
          disabled={mutation.isPending || !name.trim()}
        >
          <Plus size={16} />
          Add skill
        </button>
      </form>
      {mutation.error && <ErrorBox error={mutation.error} />}
    </section>
  );
}

function History({
  kind,
  records,
}: {
  kind: "experience" | "education";
  records: (Experience | Education)[];
}) {
  const client = useQueryClient();
  const [editing, setEditing] = useState<Experience | Education | null | false>(
    false,
  );
  const [feedback, setFeedback] = useState("");
  const mutation = useMutation({
    mutationFn: ({
      id,
      value,
      remove,
    }: {
      id?: string;
      value?: unknown;
      remove?: boolean;
    }) =>
      api(
        `/profile/${kind}${id ? `/${id}` : ""}`,
        remove ? "DELETE" : id ? "PUT" : "POST",
        value,
      ),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["profile"] });
      client.invalidateQueries({ queryKey: ["overview"] });
      setEditing(false);
      setFeedback("Changes saved.");
    },
  });
  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const f = new FormData(event.currentTarget);
    const raw = Object.fromEntries(f);
    const value = Object.fromEntries(
      Object.entries(raw).map(([k, v]) => [
        k,
        k === "technologies"
          ? splitList(String(v))
          : k === "is_current"
            ? v === "true"
              ? true
              : v === "false"
                ? false
                : null
            : v || null,
      ]),
    );
    mutation.mutate({ id: editing ? editing.id : undefined, value });
  }
  const exp = editing && "employer" in editing ? editing : null;
  const edu = editing && "institution" in editing ? editing : null;
  return (
    <section className="panel form-panel">
      <div className="section-heading">
        <div>
          <h2>{kind === "experience" ? "Experience" : "Education"}</h2>
          <p>
            {kind === "experience"
              ? "The work that shaped what you know."
              : "Your academic background and qualifications."}
          </p>
        </div>
        <button
          className="text-button"
          onClick={() => {
            setEditing(null);
            setFeedback("");
            mutation.reset();
          }}
        >
          <Plus size={16} />
          Add {kind}
        </button>
      </div>
      {records.length ? (
        records.map((item) => (
          <div key={item.id} className="history-row">
            <div>
              <strong>
                {"title" in item ? item.title : item.qualification}
              </strong>
              <span>
                {"employer" in item ? item.employer : item.institution}
              </span>
              <small>
                {dateLabel(item.start_date)} —{" "}
                {item.end_date
                  ? dateLabel(item.end_date)
                  : "End date not provided"}
              </small>
              <small>
                {"employer" in item
                  ? item.is_current === true
                    ? "Current role"
                    : item.is_current === false
                      ? "Not a current role"
                      : "Current-role status unknown"
                  : `Completion: ${label(item.completion_status || "unknown")}`}
              </small>
            </div>
            <button
              className="icon-button"
              aria-label={`Edit ${kind} ${"title" in item ? item.title : item.qualification}`}
              onClick={() => {
                setEditing(item);
                mutation.reset();
              }}
            >
              <Pencil size={16} />
            </button>
            <button
              className="icon-button"
              aria-label={`Delete ${kind} ${"title" in item ? item.title : item.qualification}`}
              disabled={mutation.isPending}
              onClick={() => mutation.mutate({ id: item.id, remove: true })}
            >
              <Trash2 size={16} />
            </button>
          </div>
        ))
      ) : (
        <p className="muted">
          No {kind} added yet. You can leave this section incomplete.
        </p>
      )}
      {editing !== false && (
        <form
          onSubmit={submit}
          className="inset-form"
          key={editing?.id || "new"}
        >
          <h3>
            {editing ? "Edit" : "Add"} {kind}
          </h3>
          <div className="form-grid">
            {kind === "experience" ? (
              <>
                <Field label="Employer or organization">
                  <input
                    name="employer"
                    defaultValue={exp?.employer}
                    required
                    maxLength={200}
                  />
                </Field>
                <Field label="Job title">
                  <input
                    name="title"
                    defaultValue={exp?.title}
                    required
                    maxLength={200}
                  />
                </Field>
                <Field label="Current-role status">
                  <select
                    name="is_current"
                    defaultValue={
                      exp?.is_current == null ? "" : String(exp.is_current)
                    }
                  >
                    <option value="">Unknown</option>
                    <option value="true">Current role</option>
                    <option value="false">Not a current role</option>
                  </select>
                </Field>
              </>
            ) : (
              <>
                <Field label="Institution">
                  <input
                    name="institution"
                    defaultValue={edu?.institution}
                    required
                    maxLength={200}
                  />
                </Field>
                <Field label="Qualification">
                  <input
                    name="qualification"
                    defaultValue={edu?.qualification}
                    required
                    maxLength={200}
                  />
                </Field>
                <Field label="Field of study">
                  <input
                    name="field_of_study"
                    defaultValue={edu?.field_of_study || ""}
                    maxLength={200}
                  />
                </Field>
                <Field label="Education completion">
                  <select
                    name="completion_status"
                    defaultValue={edu?.completion_status || "unknown"}
                  >
                    <option value="unknown">Unknown</option>
                    <option value="in_progress">In progress</option>
                    <option value="completed">
                      Completed (candidate confirmed)
                    </option>
                  </select>
                </Field>
              </>
            )}
            <Field label="Start date">
              <input
                name="start_date"
                type="date"
                defaultValue={editing?.start_date || ""}
              />
            </Field>
            <Field label="End date (optional)">
              <input
                name="end_date"
                type="date"
                defaultValue={editing?.end_date || ""}
              />
            </Field>
          </div>
          {kind === "experience" && (
            <>
              <Field label="Responsibilities">
                <textarea
                  name="responsibilities"
                  defaultValue={exp?.responsibilities || ""}
                  maxLength={10000}
                />
              </Field>
              <Field label="Achievements">
                <textarea
                  name="achievements"
                  defaultValue={exp?.achievements || ""}
                  maxLength={10000}
                />
              </Field>
              <Field
                label="Technologies and skills"
                hint="Separate with commas."
              >
                <input
                  name="technologies"
                  defaultValue={exp?.technologies.join(", ") || ""}
                />
              </Field>
            </>
          )}
          {mutation.error && <ErrorBox error={mutation.error} />}
          <div className="form-actions">
            <button
              type="button"
              className="secondary"
              onClick={() => setEditing(false)}
            >
              Cancel
            </button>
            <button className="primary" disabled={mutation.isPending}>
              Save {kind}
            </button>
          </div>
        </form>
      )}
      {editing === false && mutation.error && (
        <ErrorBox error={mutation.error} />
      )}
      {feedback && (
        <p className="success" role="status">
          {feedback}
        </p>
      )}
    </section>
  );
}
