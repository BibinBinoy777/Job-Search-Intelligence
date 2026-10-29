import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { RefreshCw, ScanSearch, Info } from "lucide-react";
import { api, ApiError } from "../../services/api-client";
import { Empty, ErrorBox, label, Loading } from "../../components/ui";
import type { Match, Pair, Refresh, SkillAssessment } from "./types";

export const eligibilityLabel = (state: string) =>
  ({
    confirmed_compatible: "Documented constraints compatible",
    confirmed_mismatch: "Explicit constraint mismatch",
    unknown: "Eligibility needs review",
    not_applicable: "Not applicable",
  })[state] || state;
const componentNames: Record<string, string> = {
  required_skills: "Required-skill evidence",
  preferred_skills: "Preferred-skill evidence",
  experience: "Experience context",
  role: "Role relevance",
  location: "Location preferences",
  preferences: "Other preferences",
};

export default function MatchAnalysis({ jobId }: { jobId: string }) {
  const client = useQueryClient();
  const q = useQuery({
    queryKey: ["match", jobId],
    queryFn: () => api<Pair>(`/jobs/${jobId}/match`),
    refetchOnMount: "always",
  });
  const refresh = useMutation({
    mutationFn: () =>
      api<Refresh>("/matches/refresh", "POST", { job_ids: [jobId] }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["match", jobId] });
      client.invalidateQueries({ queryKey: ["matches"] });
      client.invalidateQueries({ queryKey: ["matching-status"] });
      client.invalidateQueries({ queryKey: ["jobs"] });
      client.invalidateQueries({ queryKey: ["comparison"] });
    },
  });
  return (
    <section className="panel form-panel match-analysis" id="match-analysis">
      <div className="section-heading">
        <div>
          <h2>
            <ScanSearch size={18} />
            Your match analysis
          </h2>
          <p>
            Application assessment based on your recorded profile, separate from
            the vacancy’s original statements.
          </p>
        </div>
        <button
          className="secondary"
          disabled={refresh.isPending || q.isFetching}
          onClick={() => refresh.mutate()}
        >
          <RefreshCw size={14} />
          {refresh.isPending ? "Assessing…" : "Assess this job"}
        </button>
      </div>
      {refresh.error && <ErrorBox error={refresh.error} />}
      {refresh.data?.status === "partial" && (
        <div className="source-warning">
          This assessment did not finish completely. Existing results have not
          been marked freshly calculated.
        </div>
      )}
      {q.isPending || q.isFetching ? (
        <Loading />
      ) : q.error ? (
        q.error instanceof ApiError && q.error.status === 404 ? (
          <Empty
            title="Start with your profile"
            action={
              <Link className="secondary" to="/profile">
                Create profile
              </Link>
            }
          >
            Add your own skills and experience before calculating a match.
          </Empty>
        ) : (
          <ErrorBox error={q.error} retry={() => q.refetch()} />
        )
      ) : q.data?.match ? (
        <AssessmentDetails match={q.data.match} />
      ) : (
        <Empty title="Not assessed yet">
          No score has been calculated. Use Assess this job to compare your
          recorded qualifications with this available vacancy.
        </Empty>
      )}
    </section>
  );
}

export function AssessmentDetails({ match: m }: { match: Match }) {
  const a = m.assessment;
  return (
    <>
      {m.is_stale && (
        <div className="source-warning" role="status">
          Previous assessment · your profile, the job, ranking rules or
          availability evidence changed. Refresh before relying on this score.
        </div>
      )}
      <div className="match-summary">
        <div className="match-score">
          <strong>{m.score === null ? "—" : m.score.toFixed(1)}</strong>
          <span>
            {m.score === null ? "Insufficient information" : "/ 100 relevance"}
          </span>
        </div>
        <div>
          <span
            className={`badge ${m.eligibility_status === "confirmed_mismatch" ? "rejected" : ""}`}
          >
            {eligibilityLabel(m.eligibility_status)}
          </span>
          <p>
            {m.score === null
              ? "Add professional skills, experience or project evidence. A resume is not required."
              : "A relative record-based relevance estimate. It is not your probability of an interview or offer."}
          </p>
          <small>
            Requirement evidence:{" "}
            {a.evidence_coverage.value === null
              ? "not measurable"
              : `${Math.round(a.evidence_coverage.value * 100)}%`}{" "}
            · Applicable scoring weight: {Math.round(a.weight_coverage * 100)}%
          </small>
        </div>
      </div>
      <div className="match-explanation-grid">
        <div>
          <h3>What supports this assessment</h3>
          {a.positive_factors.length ? (
            <ul>
              {a.positive_factors.map((p, i) => (
                <li key={i}>{p.text}</li>
              ))}
            </ul>
          ) : (
            <p className="muted small">
              No positive professional factors were established from the
              available information.
            </p>
          )}
          <h3>Requirements to review</h3>
          {a.concerns.length ? (
            <ul>
              {a.concerns.map((c, i) => (
                <li key={i}>
                  {c.text}
                  {c.skills?.length ? ` ${c.skills.join(", ")}.` : ""}
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted small">
              No specific differences identified. This does not establish that
              every requirement is satisfied.
            </p>
          )}
        </div>
        <div>
          <h3>Component breakdown</h3>
          <div className="component-list">
            {Object.entries(a.features).map(([key, feature]) => (
              <div key={key}>
                <span>{componentNames[key] || label(key)}</span>
                <strong>
                  {feature.value === null
                    ? "Unavailable"
                    : `${Math.round(feature.value * 100)}%`}
                </strong>
                <small>{label(feature.reason)}</small>
              </div>
            ))}
          </div>
          <p className="small muted">
            Only available components contribute. Different coverage means
            different score bases; the numbers alone are not a complete
            comparison.
          </p>
        </div>
      </div>
      <SkillsEvidence
        title="Required skill evidence"
        items={a.skills.required}
      />
      <SkillsEvidence
        title="Preferred skill evidence"
        items={a.skills.preferred}
      />
      <details className="match-evidence">
        <summary>Eligibility and source constraints</summary>
        <ul>
          {a.eligibility.checks.map((check, i) => (
            <li key={i}>
              <strong>{eligibilityLabel(check.status)}</strong>
              <p>{check.message}</p>
            </li>
          ))}
        </ul>
      </details>
      <details className="match-evidence">
        <summary>Unknowns and extraction limits</summary>
        <ul>
          {a.unknown_information.map((u, i) => (
            <li key={i}>{label(u.text)}</li>
          ))}
        </ul>
        {a.skills.ambiguous_mentions.length > 0 && (
          <p className="small muted">
            Incidental/ambiguous mentions, not mandatory requirements:{" "}
            {a.skills.ambiguous_mentions.map((s) => s.name).join(", ")}.
          </p>
        )}
      </details>
      <div className="match-footnote">
        <Info size={14} />
        <span>
          Calculated {new Date(m.generated_at).toLocaleString()} ·{" "}
          {m.ranking_version} ·{" "}
          {m.is_stale ? "Previous result" : "Current recorded inputs"}
        </span>
      </div>
    </>
  );
}

function SkillsEvidence({
  title,
  items,
}: {
  title: string;
  items: SkillAssessment[];
}) {
  return (
    <details className="match-evidence">
      <summary>
        {title} · {items.filter((i) => i.state === "evidenced").length}/
        {items.length} evidenced
      </summary>
      {items.length ? (
        items.map((item) => (
          <article key={item.key}>
            <h4>
              {item.name}
              <span className="badge">
                {item.state === "evidenced"
                  ? "Documented evidence"
                  : "Not evidenced in your profile"}
              </span>
            </h4>
            <div className="evidence-columns">
              <div>
                <strong>Vacancy evidence</strong>
                {item.job_evidence.length ? (
                  item.job_evidence.map((e, i) => (
                    <blockquote key={i}>
                      {e.section && <small>{e.section}</small>}
                      {e.text}
                      <small>
                        {e.origin === "structured"
                          ? "Source skill field"
                          : "Original source span"}
                      </small>
                    </blockquote>
                  ))
                ) : (
                  <p className="small muted">
                    Source excerpts unavailable for this historical listing.
                  </p>
                )}
              </div>
              <div>
                <strong>Your recorded evidence</strong>
                {item.candidate_evidence.length ? (
                  item.candidate_evidence.map((e, i) => (
                    <blockquote key={i}>
                      {e.text}
                      <small>
                        {e.kind === "explicit"
                          ? "Explicitly recorded"
                          : "Derived from recorded professional text"}{" "}
                        · {(e.path || "profile").split("/")[0]}
                      </small>
                    </blockquote>
                  ))
                ) : (
                  <p className="small muted">
                    No evidence found in the available profile. This does not
                    mean you lack the skill.
                  </p>
                )}
              </div>
            </div>
          </article>
        ))
      ) : (
        <p className="small muted">
          No reliable requirements of this type were identified. The component
          is unavailable.
        </p>
      )}
    </details>
  );
}
