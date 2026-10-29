import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../../services/api-client";
import {
  Empty,
  ErrorBox,
  Field,
  Loading,
  PageHeading,
  label,
} from "../../components/ui";
import type { Additional, Career, Filters, Listing, Statistic } from "./types";

export function Listings({ items }: { items: Listing[] }) {
  return (
    <ul className="career-listings">
      {items.map((item) => (
        <li key={item.id}>
          <Link to={item.href}>{item.title}</Link>
          <span>
            {item.location || "Location not supplied"} · {item.source_name} ·{" "}
            {item.availability}
          </span>
        </li>
      ))}
    </ul>
  );
}
function AdditionalRequirements({ items }: { items: Additional[] }) {
  return items.length ? (
    <details>
      <summary>
        Qualifications, experience and credential requirements to investigate (
        {items.length} examples)
      </summary>
      <ul>
        {items.map((item, i) => (
          <li key={`${item.job_id}-${i}`}>
            <strong>{label(item.category)}</strong>
            <blockquote>{item.requirement.evidence.text}</blockquote>
            <p>{item.interpretation}</p>
            <Link to={`/jobs/${item.job_id}`}>Inspect source requirement</Link>
          </li>
        ))}
      </ul>
    </details>
  ) : (
    <p className="small muted">
      No additional qualifications were recognized by the extractor. This does
      not establish that none exist.
    </p>
  );
}
function SkillSupport({ item }: { item: Statistic }) {
  return (
    <details>
      <summary>Inspect {item.name} evidence</summary>
      <p>
        {item.observation_strength} · {item.count} of {item.denominator}{" "}
        eligible relevant listings (
        {item.percentage === null
          ? "percentage unavailable"
          : `${item.percentage}%`}
        ). Required {item.required_count}; preferred {item.preferred_count}.
      </p>
      {item.requirements.map((r, i) => (
        <div key={`${r.job_id}-${i}`}>
          <p>
            {label(r.category)} · {r.extraction}
          </p>
          {r.evidence.map((e, j) => (
            <blockquote key={j}>
              <p>{e.text}</p>
              <footer>
                Listing field: {e.field} · {e.origin} · Exact source span{" "}
                {e.start}–{e.end}
              </footer>
            </blockquote>
          ))}
        </div>
      ))}
      <Listings items={item.supporting_listings} />
      {item.support_truncated && (
        <p>
          Representative evidence is limited to 20 listings; the displayed count
          covers the full examined population.
        </p>
      )}
    </details>
  );
}

export default function CareerPage() {
  const [params, setParams] = useSearchParams();
  const [destination, setDestination] = useState("");
  const allowed = [
    "target_role",
    "origin_role",
    "location",
    "source_id",
    "published_after",
    "published_before",
    "requirement_kind",
  ];
  const filters = Object.fromEntries(
    allowed
      .filter((key) => params.get(key))
      .map((key) => [key, params.get(key)!]),
  ) as Filters;
  const query = useQuery({
    queryKey: ["career", filters],
    queryFn: () => api<Career>("/career/overview", "POST", filters),
    refetchOnMount: "always",
    refetchOnWindowFocus: "always",
    staleTime: 0,
  });
  if (
    query.error instanceof ApiError &&
    query.error.status === 404 &&
    !filters.source_id
  )
    return (
      <Empty
        title="Start with your existing profile"
        action={
          <Link className="primary" to="/profile">
            Create candidate profile
          </Link>
        }
      >
        Career intelligence uses your own confirmed and recorded qualifications.
        A resume is optional.
      </Empty>
    );
  const data = query.data;
  const transition = destination
    ? data?.transitions.find((t) => t.destination_id === destination)
    : data?.transitions[0];
  return (
    <>
      <PageHeading
        eyebrow="EVIDENCE TO YOUR NEXT STEP"
        title="Career intelligence."
        description="Understand your recorded strengths, inspect requirements, and choose what to investigate next."
        action={
          <button
            className="secondary"
            disabled={query.isFetching}
            onClick={() => query.refetch()}
          >
            {query.isFetching ? "Analyzing…" : "Update career analysis"}
          </button>
        }
      />
      <div className="discovery-notice">
        These observations describe collected listings in this dataset. They do
        not establish hiring eligibility or represent the whole labor market.
      </div>
      <nav className="career-section-nav" aria-label="Career sections">
        {[
          "Your skills",
          "Skills to develop",
          "Roles to explore",
          "Career paths",
          "Learning plan",
          "Market evidence",
        ].map((name, i) => (
          <a key={name} href={`#career-${i}`}>
            {name}
          </a>
        ))}
      </nav>
      <section className="panel form-panel">
        <h2>Choose the evidence scope</h2>
        <form
          key={params.toString()}
          onSubmit={(e) => {
            e.preventDefault();
            const form = new FormData(e.currentTarget);
            const next = new URLSearchParams();
            form.forEach((value, key) => {
              if (value)
                next.set(
                  key,
                  key.startsWith("published_")
                    ? `${value}T00:00:00Z`
                    : String(value),
                );
            });
            setDestination("");
            setParams(next);
          }}
        >
          <div className="form-grid">
            <Field
              label="Target role"
              hint="Leave blank to use saved target titles, or profile-skill overlap if none exist."
            >
              <input
                name="target_role"
                defaultValue={filters.target_role || ""}
                maxLength={150}
                placeholder="e.g. Data analyst"
              />
            </Field>
            <Field
              label="Listing location"
              hint="Literal source location, not inferred country or work authorization."
            >
              <input
                name="location"
                defaultValue={filters.location || ""}
                maxLength={150}
              />
            </Field>
            <Field
              label="Source ID"
              hint="Optional UUID; source names and IDs are listed in Market evidence."
            >
              <input
                name="source_id"
                defaultValue={filters.source_id || ""}
                maxLength={36}
              />
            </Field>
            <Field label="Requirement category">
              <select
                name="requirement_kind"
                defaultValue={filters.requirement_kind || "all"}
              >
                <option value="all">Required and preferred</option>
                <option value="required">Required only</option>
                <option value="preferred">Preferred only</option>
              </select>
            </Field>
            <Field
              label="Published on or after"
              hint="UTC day boundary; unknown publication dates are excluded."
            >
              <input
                name="published_after"
                type="date"
                defaultValue={filters.published_after?.slice(0, 10) || ""}
              />
            </Field>
            <Field label="Published before" hint="Exclusive UTC day boundary.">
              <input
                name="published_before"
                type="date"
                defaultValue={filters.published_before?.slice(0, 10) || ""}
              />
            </Field>
            {!!data?.origin_roles.length && (
              <Field label="Career path starting role">
                <select
                  name="origin_role"
                  defaultValue={filters.origin_role || ""}
                >
                  <option value="">
                    Use recorded experience, if available
                  </option>
                  {data.origin_roles.map((title) => (
                    <option key={title} value={title}>
                      {title}
                    </option>
                  ))}
                </select>
              </Field>
            )}
          </div>
          <button className="primary" disabled={query.isFetching}>
            Analyze this scope
          </button>{" "}
          <Link to="/settings">Update saved target roles</Link>
        </form>
      </section>
      {query.isPending ? (
        <Loading />
      ) : query.error ? (
        <ErrorBox error={query.error} retry={() => query.refetch()} />
      ) : (
        data && (
          <>
            <p className="small muted">
              {data.analysis_version} · Calculated{" "}
              {new Date(data.generated_at).toLocaleString()} · Profile evidence:{" "}
              {label(data.profile_completeness)}. One shared analysis for this
              scope.
            </p>
            {data.notices.map((n) => (
              <p className="small muted" key={n}>
                {n}
              </p>
            ))}
            <section id="career-0" className="career-section">
              <div className="section-heading">
                <h2>1. Your skills</h2>
                <Link to="/profile">Review profile evidence</Link>
              </div>
              <p>
                Confirmed means candidate-recorded, not independently verified.
                Unconfirmed resume suggestions remain outside role-overlap
                calculations.
              </p>
              {data.candidate_skills.length ? (
                <div className="career-skills">
                  {data.candidate_skills.map((s) => (
                    <article className="panel form-panel" key={s.key}>
                      <h3>{s.name}</h3>
                      <span className="badge">{label(s.status)}</span>
                      <p>{s.note}</p>
                      <details>
                        <summary>Qualification references for {s.name}</summary>
                        <ul>
                          {s.sources.map((source, i) => (
                            <li key={i}>
                              {source.path ? (
                                <Link to="/profile">
                                  Profile record: {source.path}
                                </Link>
                              ) : (
                                <Link
                                  to={`/resumes?extraction=${source.extraction_id}`}
                                >
                                  Resume proposal · {label(source.review_state)}
                                </Link>
                              )}
                            </li>
                          ))}
                        </ul>
                      </details>
                    </article>
                  ))}
                </div>
              ) : (
                <Empty title="No skill evidence recorded">
                  Add actual skill or qualification evidence in your profile, or
                  use the resume review workflow. No strengths have been
                  invented.
                </Empty>
              )}
            </section>
            <section id="career-1" className="career-section">
              <h2>2. Skills to develop or evidence</h2>
              <p>
                {data.market.relevant_listings} eligible relevant listings ·{" "}
                {data.market.target_roles.length
                  ? `Target: ${data.market.target_roles.join(", ")}`
                  : "Initial scope: recorded skill overlap"}
                . Missing profile evidence does not prove a lack of ability.
              </p>
              {data.gaps.length ? (
                data.gaps.map((gap) => (
                  <article
                    key={gap.key}
                    className="panel form-panel career-gap"
                  >
                    <div className="section-heading">
                      <h3>
                        {gap.priority}. {gap.name}
                      </h3>
                      <span className="badge">
                        {gap.candidate_status === "not_evidenced"
                          ? "Not evidenced in your profile"
                          : "Resume evidence awaiting confirmation"}
                      </span>
                    </div>
                    <p>{gap.priority_reason}</p>
                    <p>{gap.relationship}</p>
                    <p>
                      <strong>Next action:</strong> {gap.next_action}
                    </p>
                    <SkillSupport item={gap} />
                    <a className="text-button" href={`#learn-${gap.key}`}>
                      Explore learning or review action
                    </a>
                  </article>
                ))
              ) : (
                <Empty title="No supported skill gaps to rank">
                  The sample may be empty, requirements may be incomplete, or
                  recognized skills are already evidenced. This does not
                  establish that all job requirements are met.
                </Empty>
              )}
            </section>
            <section id="career-2" className="career-section">
              <h2>3. Roles to explore</h2>
              <p>
                Role discovery examines {data.market.unique_scoped_listings}{" "}
                distinct scoped listings. Ranking uses recorded skill overlap,
                then overlap count and sample support; it is an exploration
                heuristic.
              </p>
              {data.roles.length ? (
                data.roles.map((role) => (
                  <article key={role.id} className="panel form-panel">
                    <h3>{role.title}</h3>
                    <span className="badge">{role.evidence_strength}</span>
                    <p>{role.reason}</p>
                    <p>
                      <strong>Supporting skills:</strong>{" "}
                      {role.overlap.join(", ")}
                    </p>
                    <p>
                      <strong>Required skills not evidenced:</strong>{" "}
                      {role.missing_skills.join(", ") ||
                        "None recognized; other requirements may remain."}
                    </p>
                    <p>
                      {role.listing_count} supporting listing(s).{" "}
                      {role.next_action}
                    </p>
                    <details>
                      <summary>Why {role.title} is suggested</summary>
                      <ul>
                        {role.candidate_sources.map((s, i) => (
                          <li key={i}>
                            {s.skill} · {label(s.status)} ·{" "}
                            <Link to="/profile">
                              Inspect recorded qualifications
                            </Link>
                          </li>
                        ))}
                      </ul>
                      <AdditionalRequirements
                        items={role.additional_requirements}
                      />
                      <Listings items={role.representative_listings} />
                      {role.limitations.map((n) => (
                        <p className="small muted" key={n}>
                          {n}
                        </p>
                      ))}
                    </details>
                    <button
                      className="text-button"
                      onClick={() => {
                        setDestination(role.id);
                        document
                          .getElementById("career-3")
                          ?.scrollIntoView({ behavior: "smooth" });
                      }}
                    >
                      Explore path to {role.title}
                    </button>{" "}
                    <button
                      className="text-button"
                      onClick={() => {
                        const next = new URLSearchParams(params);
                        next.set("target_role", role.title);
                        next.delete("origin_role");
                        setParams(next);
                      }}
                    >
                      Use {role.title} as target
                    </button>
                  </article>
                ))
              ) : (
                <Empty title="Insufficient evidence for adjacent roles">
                  A title alone cannot establish role fit. Add relevant profile
                  evidence or adjust the listing scope.
                </Empty>
              )}
            </section>
            <section id="career-3" className="career-section">
              <h2>4. Career paths</h2>
              <p>
                Select a starting role in the scope controls and choose a
                destination. Shared skills support a pathway to investigate, not
                a promised progression.
              </p>
              {transition ? (
                <article className="panel form-panel">
                  <Field label="Explore destination">
                    <select
                      value={transition.destination_id}
                      onChange={(e) => setDestination(e.target.value)}
                    >
                      {data.transitions.map((t) => (
                        <option value={t.destination_id} key={t.destination_id}>
                          {t.destination}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <ol className="career-path">
                    <li>
                      <strong>{transition.origin}</strong>
                      <p>{label(transition.origin_kind)}</p>
                    </li>
                    <li>
                      <strong>Transfer and investigate</strong>
                      <p>
                        Transferable:{" "}
                        {transition.transferable_skills.join(", ")}
                      </p>
                      <p>
                        Required skill evidence to investigate:{" "}
                        {transition.skills_to_investigate.join(", ") ||
                          "No additional skills recognized; inspect the full requirements."}
                      </p>
                    </li>
                    <li>
                      <strong>{transition.destination}</strong>
                      <p>{transition.evidence_strength}</p>
                    </li>
                  </ol>
                  <AdditionalRequirements
                    items={transition.additional_requirements}
                  />
                  <Listings items={transition.supporting_listings} />
                  <ul>
                    {transition.next_steps.map((s) => (
                      <li key={s}>{s}</li>
                    ))}
                  </ul>
                  {transition.limitations.map((n) => (
                    <p className="small muted" key={n}>
                      {n}
                    </p>
                  ))}
                </article>
              ) : (
                <Empty title="Insufficient evidence for this transition">
                  Choose a recorded or collected starting role with evidenced
                  transferable skills. No intermediate roles, timeline or salary
                  improvement has been invented.
                </Empty>
              )}
            </section>
            <section id="career-4" className="career-section">
              <h2>5. Learning plan</h2>
              <p>
                Actions follow the top 12 gaps in the current target scope.
                Verification is a dated check of resource identity/content, not
                a course credential or employment guarantee.
              </p>
              {data.learning.length ? (
                data.learning.map((action) => (
                  <article
                    id={`learn-${action.skill_key}`}
                    className="panel form-panel"
                    key={action.skill_key}
                  >
                    <h3>{action.skill}</h3>
                    <p>{action.why}</p>
                    <p>{action.practice}</p>
                    {action.action_kind === "review_existing_evidence" && (
                      <Link to="/resumes">
                        Review existing resume evidence first
                      </Link>
                    )}
                    <ul>
                      {action.resources.map((resource, i) => (
                        <li key={i}>
                          <strong>{resource.title}</strong>
                          <p>
                            {resource.verification_status === "verified"
                              ? "Verified resource identity/content"
                              : resource.verification_status ===
                                  "verification_stale"
                                ? "Verification stale; check the destination"
                                : "Unverified learning direction"}
                            {resource.verified_on
                              ? ` · Checked ${resource.verified_on}`
                              : ""}
                          </p>
                          <p>
                            {resource.provider} {resource.level}
                          </p>
                          {resource.url && (
                            <a
                              href={resource.url}
                              target="_blank"
                              rel="noopener noreferrer"
                            >
                              Open {resource.title}
                            </a>
                          )}
                          {resource.verification_evidence && (
                            <details>
                              <summary>Verification evidence</summary>
                              <p>{resource.verification_evidence}</p>
                              <a
                                href={resource.verification_source!}
                                target="_blank"
                                rel="noopener noreferrer"
                              >
                                Provider source checked
                              </a>
                            </details>
                          )}
                        </li>
                      ))}
                    </ul>
                  </article>
                ))
              ) : (
                <Empty title="No skill-specific learning actions yet">
                  No supported gaps are available in this scope. You can still
                  review actual qualifications and choose a career direction.
                </Empty>
              )}
            </section>
            <section id="career-5" className="career-section">
              <h2>6. Market evidence</h2>
              <div className="panel form-panel">
                <p>
                  <strong>
                    {data.market.relevant_listings} eligible relevant listings
                  </strong>{" "}
                  in the denominator ·{" "}
                  {data.market.listings_with_usable_requirements} with
                  recognized requirements.
                </p>
                <p>
                  {data.market.stored_listing_records} stored records;{" "}
                  {data.market.scoped_records} pass scope/availability;{" "}
                  {data.market.analyzed_records} examined;{" "}
                  {data.market.duplicate_records_excluded} exact-content
                  duplicates excluded; {data.market.excluded_unavailable}{" "}
                  unavailable records excluded within the selected
                  source/location/date scope.
                </p>
                {data.market.population_truncated && (
                  <p role="status">
                    Partial population. Narrow the filters before treating the
                    sample as complete.
                  </p>
                )}
                <p>{data.market.denominator_definition}</p>
                <p>{data.market.relevance_basis}</p>
                <p>{data.market.geography_definition}</p>
                <h3>Sources in the denominator</h3>
                {data.market.sources.length ? (
                  <ul>
                    {data.market.sources.map((s) => (
                      <li key={s.id || s.name}>
                        {s.name}: {s.count} listing(s)
                        {s.id && <span> · ID {s.id}</span>}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p>No sources in the relevant sample.</p>
                )}
                <h3>Source-supplied locations</h3>
                <ul>
                  {data.market.locations.map((l) => (
                    <li key={l.label}>
                      {l.label}: {l.count} listing(s)
                    </li>
                  ))}
                </ul>
                <p>
                  Publication range:{" "}
                  {data.market.publication_range.earliest
                    ? new Date(
                        data.market.publication_range.earliest,
                      ).toLocaleDateString()
                    : "Unknown"}{" "}
                  to{" "}
                  {data.market.publication_range.latest
                    ? new Date(
                        data.market.publication_range.latest,
                      ).toLocaleDateString()
                    : "Unknown"}
                  ; {data.market.publication_range.unknown_count} dates not
                  supplied.
                </p>
                <ul>
                  {data.market.limitations.map((n) => (
                    <li key={n}>{n}</li>
                  ))}
                </ul>
              </div>
              {data.skill_statistics.length > 0 && (
                <div className="career-table-wrap">
                  <table className="career-table">
                    <caption>
                      Recognized skills in this dataset (
                      {label(data.market.requirement_kind)} requirements)
                    </caption>
                    <thead>
                      <tr>
                        <th scope="col">Skill</th>
                        <th scope="col">Required</th>
                        <th scope="col">Preferred</th>
                        <th scope="col">Listings / denominator</th>
                        <th scope="col">Profile evidence</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.skill_statistics.map((s) => (
                        <tr key={s.key}>
                          <th scope="row">{s.name}</th>
                          <td>{s.required_count}</td>
                          <td>{s.preferred_count}</td>
                          <td>
                            {s.count} / {s.denominator} ({s.percentage}%)
                          </td>
                          <td>{label(s.candidate_status)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          </>
        )
      )}
    </>
  );
}
