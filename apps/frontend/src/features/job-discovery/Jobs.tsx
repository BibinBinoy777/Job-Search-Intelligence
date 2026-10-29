import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  ArrowRight,
  Bookmark,
  BriefcaseBusiness,
  ExternalLink,
  MapPin,
} from "lucide-react";
import { api } from "../../services/api-client";
import type { Job } from "../../types";
import SearchExperience from "./SearchExperience";
import { CompareButton } from "./Comparison";
import MatchAnalysis from "../job-matching/MatchAnalysis";
import {
  dateLabel,
  Empty,
  ErrorBox,
  label,
  Loading,
  PageHeading,
} from "../../components/ui";

export function JobCard({ job, saved = false }: { job: Job; saved?: boolean }) {
  const client = useQueryClient();
  const isSaved = saved || job.is_saved;
  const mutation = useMutation({
    mutationFn: () => api(`/jobs/${job.id}/save`, isSaved ? "DELETE" : "PUT"),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["jobs"] });
      client.invalidateQueries({ queryKey: ["job", job.id] });
      client.invalidateQueries({ queryKey: ["saved"] });
      client.invalidateQueries({ queryKey: ["overview"] });
      client.invalidateQueries({ queryKey: ["comparison"] });
    },
  });
  return (
    <article className="job-card">
      <div className="job-card-top">
        <span className="employer-icon">{job.employer[0]}</span>
        <div>
          <span className="muted small">{job.employer}</span>
          <h2>
            <Link to={`/jobs/${job.id}`}>{job.title}</Link>
          </h2>
        </div>
        <button
          aria-label={isSaved ? `Unsave ${job.title}` : `Save ${job.title}`}
          className={`save-button ${isSaved ? "is-saved" : ""}`}
          disabled={mutation.isPending}
          onClick={() => mutation.mutate()}
        >
          <Bookmark size={19} fill={isSaved ? "currentColor" : "none"} />
        </button>
      </div>
      <div className="job-meta">
        <span>
          <MapPin size={14} />
          {job.location || "Location not provided"}
        </span>
        <span>
          <BriefcaseBusiness size={14} />
          {label(job.work_arrangement)}
        </span>
        <span>{label(job.employment_type)}</span>
      </div>
      <p className="job-excerpt">
        {job.description.slice(0, 220)}
        {job.description.length > 220 ? "…" : ""}
      </p>
      <p className="job-salary">{salaryLabel(job)}</p>
      <div className="job-dates">
        <span>Published: {dateLabel(job.published_at)}</span>
        <span>Source updated: {dateLabel(job.source_updated_at || null)}</span>
        <span>
          Verified:{" "}
          {job.last_verified_at
            ? dateLabel(job.last_verified_at)
            : "Not verified"}
        </span>
      </div>
      <div className="job-card-footer">
        <span>
          {job.source?.adapter_key === "himalayas" ? (
            <a
              href={job.source_url || "https://himalayas.app"}
              target="_blank"
              rel="noreferrer"
            >
              Data: Himalayas ↗
            </a>
          ) : (
            job.source?.name || "Source not provided"
          )}{" "}
          · <span className="badge">{label(job.status)}</span>
        </span>
        <Link to={`/jobs/${job.id}`} className="text-button">
          View opportunity
          <ArrowRight size={15} />
        </Link>
      </div>
      <CompareButton job={job} />
      {mutation.isSuccess && (
        <p className="small" role="status">
          Saved-job change confirmed.
        </p>
      )}
      {mutation.error && <ErrorBox error={mutation.error} />}
    </article>
  );
}

export default function JobsPage() {
  return <SearchExperience />;
}

export function JobDetailPage() {
  const { id } = useParams();
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ["job", id],
    queryFn: () => api<Job>(`/jobs/${id}`),
  });
  const [tracked, setTracked] = useState(false);
  const create = useMutation({
    mutationFn: () =>
      api("/applications", "POST", { job_id: id, status: "interested" }),
    onSuccess: () => {
      setTracked(true);
      client.invalidateQueries({ queryKey: ["applications"] });
      client.invalidateQueries({ queryKey: ["overview"] });
      client.invalidateQueries({ queryKey: ["comparison"] });
    },
  });
  const save = useMutation({
    mutationFn: () =>
      api(`/jobs/${id}/save`, query.data?.is_saved ? "DELETE" : "PUT"),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["job", id] });
      client.invalidateQueries({ queryKey: ["jobs"] });
      client.invalidateQueries({ queryKey: ["saved"] });
      client.invalidateQueries({ queryKey: ["overview"] });
      client.invalidateQueries({ queryKey: ["comparison"] });
    },
  });
  if (query.isPending) return <Loading />;
  if (query.error)
    return <ErrorBox error={query.error} retry={() => query.refetch()} />;
  const job = query.data!;
  return (
    <>
      <Link to="/jobs" className="text-button back-link">
        <ArrowLeft size={16} />
        All opportunities
      </Link>
      <PageHeading
        eyebrow={job.employer.toUpperCase()}
        title={job.title}
        description={`${job.location || "Location not provided"} · ${label(job.work_arrangement)} · ${label(job.employment_type)}`}
      />
      <div className="detail-layout">
        <article className="panel detail-body">
          <div className="section-heading">
            <h2>About this opportunity</h2>
            <span className="badge">{label(job.status)}</span>
          </div>
          <p className="preserve-text">{job.description}</p>
          {job.availability === "verification_stale" && (
            <p className="source-warning">
              Availability needs a fresh source check. The listing is hidden
              from discovery until reverified.
            </p>
          )}
          {job.responsibilities && (
            <>
              <h3>Responsibilities</h3>
              <p className="preserve-text">{job.responsibilities}</p>
            </>
          )}
          {job.qualifications && (
            <>
              <h3>Qualifications</h3>
              <p className="preserve-text">{job.qualifications}</p>
            </>
          )}
          {["required", "preferred"].map((kind) => (
            <section key={kind}>
              <h3>{label(kind)} skills</h3>
              <div className="skill-list">
                {job.skills.filter((s) => s.kind === kind).length ? (
                  job.skills
                    .filter((s) => s.kind === kind)
                    .map((s) => (
                      <span className="skill" key={s.id}>
                        {s.name}
                      </span>
                    ))
                ) : (
                  <span className="muted">Not provided.</span>
                )}
              </div>
            </section>
          ))}
          <h3>Experience</h3>
          <p>
            {job.experience_min === null && job.experience_max === null
              ? "Not provided."
              : `${job.experience_min ?? "Unspecified"} – ${job.experience_max ?? "Unspecified"} years`}
          </p>
          <h3>Salary</h3>
          <p>{salaryLabel(job)}</p>
          {job.location_restrictions && (
            <>
              <h3>Location restrictions</h3>
              <p>
                {job.location_restrictions.length
                  ? job.location_restrictions.join(", ")
                  : "Worldwide according to the source. Check the full description for additional requirements."}
              </p>
            </>
          )}
          {job.timezone_restrictions && (
            <>
              <h3>Timezone restrictions</h3>
              <p>
                {job.timezone_restrictions.length
                  ? job.timezone_restrictions
                      .map((v) =>
                        typeof v === "number"
                          ? `UTC${v >= 0 ? "+" : ""}${v}`
                          : v,
                      )
                      .join(", ")
                  : "No timezone restriction supplied."}
              </p>
            </>
          )}
          {job.source_categories?.length ? (
            <>
              <h3>Source categories</h3>
              <div className="skill-list">
                {job.source_categories.map((c, i) => (
                  <span key={`${c}-${i}`} className="skill">
                    {c}
                  </span>
                ))}
              </div>
              <p className="small muted">
                These are source taxonomy labels, not verified required skills.
              </p>
            </>
          ) : null}
        </article>
        <aside>
          <section className="panel detail-aside">
            <h2>Your next step</h2>
            <button
              className="primary wide"
              disabled={save.isPending}
              onClick={() => save.mutate()}
            >
              <Bookmark size={17} />
              {job.is_saved ? "Remove from saved" : "Save opportunity"}
            </button>
            {save.error && <ErrorBox error={save.error} />}
            <button
              className="secondary wide"
              disabled={create.isPending || tracked}
              onClick={() => create.mutate()}
            >
              <BriefcaseBusiness size={17} />
              {tracked ? "Added to tracker" : "Track application"}
            </button>
            {create.error && <ErrorBox error={create.error} />}
            {tracked && (
              <Link to="/applications" className="text-button">
                Go to applications →
              </Link>
            )}
            <small>
              Tracking keeps your notes here. You submit any application
              yourself.
            </small>
            {job.source_url && (
              <a
                className="text-button"
                href={job.source_url}
                target="_blank"
                rel="noopener noreferrer"
              >
                Open original vacancy <ExternalLink size={15} />
              </a>
            )}
            <hr />
            <h3>Source & freshness</h3>
            {job.source?.adapter_key === "himalayas" && (
              <a
                className="text-button"
                href="https://himalayas.app"
                target="_blank"
                rel="noreferrer"
              >
                Data sourced from Himalayas ↗
              </a>
            )}
            <dl>
              <dt>Source</dt>
              <dd>{job.source?.name || "Not provided"}</dd>
              <dt>Published</dt>
              <dd>{dateLabel(job.published_at)}</dd>
              <dt>Source modified</dt>
              <dd>{dateLabel(job.source_updated_at || null)}</dd>
              <dt>Source deadline</dt>
              <dd>{dateLabel(job.source_expires_at || null)}</dd>
              <dt>First seen</dt>
              <dd>{dateLabel(job.first_seen_at)}</dd>
              <dt>Last seen</dt>
              <dd>{dateLabel(job.last_seen_at)}</dd>
              <dt>Last verified</dt>
              <dd>
                {job.last_verified_at
                  ? dateLabel(job.last_verified_at)
                  : "Not verified"}
              </dd>
              <dt>Material update</dt>
              <dd>{dateLabel(job.material_updated_at)}</dd>
              <dt>Status evidence</dt>
              <dd>
                {job.status_basis ? label(job.status_basis) : "Not supplied"}
              </dd>
            </dl>
            <p className="small muted">
              A stored listing alone does not establish that a vacancy is still
              open. Check the original source before acting.
            </p>
          </section>
        </aside>
      </div>
      <CompareButton job={job} />
      <MatchAnalysis jobId={job.id} />
    </>
  );
}

export function salaryLabel(job: Job) {
  return job.salary_min === null && job.salary_max === null
    ? "Salary not provided"
    : `${job.salary_currency || "Currency unknown"} ${job.salary_min?.toLocaleString() ?? "Unspecified"} – ${job.salary_max?.toLocaleString() ?? "Unspecified"}${job.salary_period ? ` / ${job.salary_period}` : " · pay period unknown"}`;
}
