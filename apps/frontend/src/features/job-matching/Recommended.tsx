import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { RefreshCw, ArrowRight, ScanSearch } from "lucide-react";
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
import { JobCard } from "../job-discovery/Jobs";
import type { Match, MatchingStatus, Refresh } from "./types";
import { eligibilityLabel } from "./MatchAnalysis";

export default function RecommendedPage() {
  const client = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [message, setMessage] = useState("");
  const status = useQuery({
    queryKey: ["matching-status"],
    queryFn: () => api<MatchingStatus>("/matching/status"),
    refetchOnMount: "always",
  });
  const query = new URLSearchParams(params);
  query.set("page_size", "12");
  const matches = useQuery({
    queryKey: ["matches", query.toString()],
    queryFn: () => api<Page<Match>>(`/matches?${query}`),
    enabled: !!status.data,
    refetchOnMount: "always",
  });
  const refresh = useMutation({
    mutationFn: (cursor?: string) =>
      api<Refresh>(
        "/matches/refresh",
        "POST",
        cursor ? { after_job_id: cursor } : {},
      ),
    onMutate: () => setMessage(""),
    onSuccess: (r) => {
      setMessage(
        r.status === "complete"
          ? `Refresh complete: ${r.calculated} calculated, ${r.reused} unchanged results reused.`
          : `Partial refresh: ${r.calculated} calculated, ${r.failed} failed. ${r.has_more ? "More jobs remain." : "Review results before continuing."}`,
      );
      client.invalidateQueries({ queryKey: ["matching-status"] });
      client.invalidateQueries({ queryKey: ["matches"] });
      client.invalidateQueries({ queryKey: ["match"] });
      client.invalidateQueries({ queryKey: ["jobs"] });
      client.invalidateQueries({ queryKey: ["comparison"] });
    },
  });
  if (
    status.error &&
    status.error instanceof ApiError &&
    status.error.status === 404
  )
    return (
      <Empty
        title="Your profile is the starting point"
        action={
          <Link className="primary" to="/profile">
            Create candidate profile
          </Link>
        }
      >
        Recommendations need your own recorded professional information. There
        is no resume-upload requirement.
      </Empty>
    );
  function filter(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const next = new URLSearchParams();
    f.forEach((v, k) => {
      if (v) next.set(k, String(v));
    });
    setParams(next);
  }
  return (
    <>
      <PageHeading
        eyebrow="RELEVANCE YOU CAN INSPECT"
        title="Opportunities, with reasons."
        description="A transparent comparison of recorded qualifications and genuine vacancies. Every score has an evidence trail."
        action={
          <button
            className="primary"
            disabled={refresh.isPending || !status.data}
            onClick={() => refresh.mutate(undefined)}
          >
            <RefreshCw size={16} />
            {refresh.isPending ? "Calculating…" : "Refresh recommendations"}
          </button>
        }
      />
      <div className="discovery-notice">
        <ScanSearch size={17} />
        <span>
          Scores describe recorded relevance, not interview odds. Eligibility
          and evidence coverage are assessed separately.
        </span>
      </div>
      {status.isPending ? (
        <Loading />
      ) : status.error ? (
        <ErrorBox error={status.error} retry={() => status.refetch()} />
      ) : (
        <div className="matching-status">
          <span>{status.data!.current_results} current assessments</span>
          <span>{status.data!.stale_results} previous assessments</span>
          <span>{status.data!.uncalculated_jobs} uncalculated</span>
          <small>
            Last refresh:{" "}
            {status.data!.last_refresh
              ? new Date(status.data!.last_refresh.finished_at).toLocaleString()
              : "Not calculated yet"}{" "}
            · {status.data!.ranking_version}
          </small>
        </div>
      )}
      {refresh.error && <ErrorBox error={refresh.error} />}
      {message && (
        <p
          role="status"
          className={
            refresh.data?.status === "complete" ? "success" : "source-warning"
          }
        >
          {message}
        </p>
      )}
      {refresh.data?.has_more && refresh.data.next_job_id && (
        <button
          className="secondary"
          disabled={refresh.isPending}
          onClick={() => refresh.mutate(refresh.data!.next_job_id!)}
        >
          Continue remaining jobs <ArrowRight size={15} />
        </button>
      )}
      {status.data && (
        <>
          <section className="panel match-filters">
            <form onSubmit={filter} key={params.toString()}>
              <Field label="Minimum relevance">
                <input
                  name="minimum_score"
                  type="number"
                  min="0"
                  max="100"
                  defaultValue={params.get("minimum_score") || ""}
                  placeholder="Any score"
                />
              </Field>
              <Field label="Eligibility">
                <select
                  name="eligibility"
                  defaultValue={params.get("eligibility") || ""}
                >
                  <option value="">No confirmed mismatches</option>
                  <option value="confirmed_compatible">
                    Documented compatible constraints
                  </option>
                  <option value="unknown">Needs review</option>
                  <option value="confirmed_mismatch">
                    Inspect excluded constraints
                  </option>
                </select>
              </Field>
              <Field label="Required-skill evidence">
                <select
                  name="required_coverage"
                  defaultValue={params.get("required_coverage") || ""}
                >
                  <option value="">Any evidence coverage</option>
                  <option value="0.5">At least 50% evidenced</option>
                  <option value="1">
                    All identified required skills evidenced
                  </option>
                </select>
              </Field>
              <label className="show-stale">
                <input
                  type="checkbox"
                  name="include_stale"
                  value="true"
                  defaultChecked={params.get("include_stale") === "true"}
                />
                Include previous assessments
              </label>
              <button className="secondary">Apply filters</button>
            </form>
          </section>
          {matches.isPending || matches.isFetching ? (
            <Loading />
          ) : matches.error ? (
            <ErrorBox error={matches.error} retry={() => matches.refetch()} />
          ) : !matches.data?.items.length ? (
            <section className="panel">
              <Empty
                title={
                  status.data.current_results === 0
                    ? "Start with an evidence-based refresh"
                    : "No assessments match these filters"
                }
                action={
                  <Link to="/profile" className="text-button">
                    Review my profile →
                  </Link>
                }
              >
                Add skills, experience or projects, then refresh. Uncalculated
                and unsupported matches never become a fake score of zero.
                Unavailable listings and confirmed hard mismatches are excluded
                by default.
              </Empty>
            </section>
          ) : (
            <div className="recommendation-list">
              {matches.data.items.map((m) => (
                <div className="recommendation-item" key={m.id}>
                  <div className="match-strip">
                    <strong>
                      {m.score === null
                        ? "Insufficient information"
                        : `${m.score.toFixed(1)} / 100 relevance`}
                    </strong>
                    <span>{eligibilityLabel(m.eligibility_status)}</span>
                    <small>
                      {m.evidence_coverage === null
                        ? "Requirement evidence not measurable"
                        : `${Math.round(m.evidence_coverage * 100)}% requirement evidence`}{" "}
                      · {Math.round(m.assessment.weight_coverage * 100)}%
                      scoring weight assessed
                    </small>
                    {m.is_stale && (
                      <span className="badge rejected">
                        Previous assessment · refresh required
                      </span>
                    )}
                    <Link
                      to={`/jobs/${m.job.id}#match-analysis`}
                      className="text-button"
                    >
                      Inspect evidence <ArrowRight size={14} />
                    </Link>
                  </div>
                  <JobCard job={m.job} />
                </div>
              ))}
            </div>
          )}
          {matches.data && (
            <Pagination
              page={Number(params.get("page")) || 1}
              total={matches.data.total}
              change={(p) => {
                const next = new URLSearchParams(params);
                next.set("page", String(p));
                setParams(next);
              }}
            />
          )}
        </>
      )}
    </>
  );
}
