import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../../services/api-client";
import {
  Empty,
  ErrorBox,
  Field,
  label,
  Loading,
  PageHeading,
  Pagination,
} from "../../components/ui";
import type { Job, Page, Source } from "../../types";
import { JobCard } from "./Jobs";
import { ComparisonTray } from "./Comparison";
import SavedSearches from "./SavedSearches";
import { choices, readSearch } from "./search-state";
interface Summary {
  state: string;
  score: number | null;
  eligibility: string | null;
  assessment_status: string | null;
}
interface Results extends Page<Job> {
  assessments?: Record<string, Summary>;
  notices?: string[];
}
const sortLabels: Record<string, string> = {
  recent: "Most recently collected",
  text_relevance: "Best text match",
  candidate_match: "Best current candidate match",
  published_desc: "Most recently published",
  verified_desc: "Recently verified",
  title: "Job title",
  employer: "Employer",
  salary_desc: "Salary (currency & period required)",
};
export default function SearchExperience() {
  const [url, setUrl] = useSearchParams();
  const { params, error } = readSearch(url);
  const [keyword, setKeyword] = useState(params.get("q") || "");
  const [suggestionQuery, setSuggestionQuery] = useState("");
  const [showSuggestions, setShowSuggestions] = useState(false);
  useEffect(() => {
    setKeyword(url.get("q") || "");
  }, [url]);
  useEffect(() => {
    const timer = window.setTimeout(
      () => setSuggestionQuery(keyword.trim()),
      300,
    );
    return () => clearTimeout(timer);
  }, [keyword]);
  const request = new URLSearchParams(params);
  request.set("page_size", "12");
  if (!request.has("sort")) request.set("sort", "text_relevance");
  const query = useQuery({
    queryKey: ["jobs", request.toString()],
    queryFn: () => api<Results>(`/jobs?${request}`),
    enabled: !error,
    refetchOnMount: "always",
  });
  const sources = useQuery({
    queryKey: ["sources"],
    queryFn: () => api<Page<Source>>("/sources?page_size=100"),
  });
  const suggestions = useQuery({
    queryKey: ["search-suggestions", suggestionQuery],
    queryFn: () =>
      api<{ items: { kind: string; value: string }[] }>(
        `/jobs/suggestions?q=${encodeURIComponent(suggestionQuery)}&limit=8`,
      ),
    enabled:
      showSuggestions &&
      suggestionQuery.length >= 2 &&
      suggestionQuery.length <= 100,
  });
  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const next = new URLSearchParams();
    new FormData(event.currentTarget).forEach((value, key) => {
      if (String(value).trim()) next.append(key, String(value).trim());
    });
    setShowSuggestions(false);
    setUrl(next);
  }
  function input(key: string, title: string, type = "text", hint?: string) {
    return (
      <Field label={title} hint={hint}>
        <input
          name={key}
          type={type}
          defaultValue={params.get(key) || ""}
          maxLength={key === "salary_currency" ? 3 : 250}
          min={type === "number" ? 0 : undefined}
          step={type === "number" ? "any" : undefined}
        />
      </Field>
    );
  }
  function select(key: string, title: string, empty: string) {
    return (
      <Field label={title}>
        <select name={key} defaultValue={params.get(key) || ""}>
          <option value="">{empty}</option>
          {choices[key].map((value) => (
            <option key={value} value={value}>
              {sortLabels[value] || label(value)}
            </option>
          ))}
        </select>
      </Field>
    );
  }
  function remove(key: string) {
    const next = new URLSearchParams(params);
    next.delete(key);
    next.delete("page");
    setUrl(next);
  }
  const active = [...new Set(params.keys())].filter(
    (key) => !["page", "page_size"].includes(key),
  );
  return (
    <>
      <PageHeading
        eyebrow="FIND WITH CONTEXT"
        title="Find your next opportunity."
        description="Search genuine records, compare the facts, and inspect your recorded matching evidence."
      />
      <div className="discovery-notice">
        <strong>Phase 4 discovery · Phase 2 source evidence</strong>
        <span>
          Text relevance, candidate relevance and eligibility are separate.
        </span>
        <Link to="/sources">View source health →</Link>
      </div>
      <section className="panel search-panel">
        <form onSubmit={submit} key={url.toString()}>
          <div className="search-main">
            <div>
              <Field label="Search jobs">
                <input
                  name="q"
                  value={keyword}
                  onChange={(e) => {
                    setKeyword(e.target.value);
                    setShowSuggestions(true);
                  }}
                  onFocus={() => setShowSuggestions(true)}
                  maxLength={200}
                  placeholder="Title, employer, skills or keywords"
                  aria-controls="search-suggestions"
                />
              </Field>
              {showSuggestions && suggestions.data?.items.length ? (
                <ul
                  id="search-suggestions"
                  className="search-suggestions"
                  aria-label="Suggestions from stored jobs"
                >
                  {suggestions.data.items.map((item) => (
                    <li key={`${item.kind}:${item.value}`}>
                      <button
                        type="button"
                        onClick={() => {
                          setKeyword(item.value);
                          setShowSuggestions(false);
                        }}
                      >
                        {item.value}
                        <small>{label(item.kind)}</small>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
            {input("location", "Location")}
            <button className="primary">Search jobs</button>
          </div>
          <div className="filter-row">
            {select(
              "employment_type",
              "Employment type",
              "All employment types",
            )}
            {select(
              "work_arrangement",
              "Work arrangement",
              "All work arrangements",
            )}
            <Field label="Source">
              <select
                name="source_id"
                defaultValue={params.get("source_id") || ""}
              >
                <option value="">All sources</option>
                {sources.data?.items.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Sort by">
              <select
                name="sort"
                defaultValue={params.get("sort") || "text_relevance"}
              >
                {choices.sort.map((s) => (
                  <option value={s} key={s}>
                    {sortLabels[s]}
                  </option>
                ))}
              </select>
            </Field>
            <button
              type="button"
              className="text-button"
              onClick={() => {
                setUrl({});
                setKeyword("");
                setShowSuggestions(false);
              }}
            >
              Reset
            </button>
          </div>
          <details className="advanced-filters">
            <summary>
              More filters · requirements, dates, availability, salary &
              matching
            </summary>
            <div className="form-grid">
              {input("title", "Job title contains")}
              {input("employer", "Employer contains")}
              {input(
                "country",
                "Country or source region",
                "text",
                "Exact source restriction label; worldwide listings also qualify. Unknown restrictions do not.",
              )}
              {input(
                "skills",
                "Required or preferred skill",
                "text",
                "Uses structured fields and current cached requirement extraction.",
              )}
              {select("status", "Listing status", "All visible statuses")}
              {select(
                "availability_scope",
                "Listing availability",
                "Current discovery rules",
              )}
              {input("experience_min", "Minimum experience range", "number")}
              {input("experience_max", "Maximum experience range", "number")}
              {input(
                "published_after",
                "Originally published after",
                "text",
                "ISO timestamp with timezone; unknown dates are excluded.",
              )}
              {input(
                "updated_after",
                "Source updated after",
                "text",
                "ISO timestamp with timezone.",
              )}
              {input(
                "verified_after",
                "Verified after",
                "text",
                "ISO timestamp with timezone.",
              )}
              {input("salary_min", "Minimum salary", "number")}
              {input("salary_max", "Maximum salary", "number")}
              {input(
                "salary_currency",
                "Salary currency",
                "text",
                "Currency code, e.g. USD. No currency conversion.",
              )}
              {select("salary_period", "Salary period", "Not selected")}
              {input(
                "minimum_score",
                "Minimum current candidate score",
                "number",
                "Calculated and assessable only; missing is not zero.",
              )}
              {input(
                "required_coverage",
                "Minimum required-skill coverage",
                "number",
                "0–1; uses current matching evidence only.",
              )}
              {select("eligibility", "Eligibility", "Any eligibility")}
              {select(
                "match_state",
                "Assessment availability",
                "Any assessment state",
              )}
            </div>
            <p className="small muted">
              Different filters combine with AND. Salary filters exclude missing
              or incomparable bounds. Remote does not mean worldwide
              eligibility. Original publication dates are never inferred from
              updates.
            </p>
          </details>
        </form>
        {sources.error && (
          <ErrorBox error={sources.error} retry={() => sources.refetch()} />
        )}
      </section>
      <div className="active-filters" aria-label="Applied filters">
        {active.map((key) => (
          <button
            className="filter-chip"
            key={key}
            onClick={() => remove(key)}
            aria-label={`Remove ${label(key)} filter`}
          >
            {label(key)}: {params.getAll(key).join(", ")} ×
          </button>
        ))}
        {active.length > 0 && (
          <button className="text-button" onClick={() => setUrl({})}>
            Clear all filters
          </button>
        )}
      </div>
      {error && <ErrorBox error={new Error(error)} />}
      <SavedSearches params={params} load={setUrl} invalid={!!error} />
      <ComparisonTray />
      <div className="results-heading">
        <h2>
          {query.data && !error
            ? `${query.data.total} opportunities`
            : "Opportunities"}
        </h2>
        <span>Backend filtering · Deterministic ordering</span>
      </div>
      {error ? (
        <p>
          Correct the invalid filters or reset the search. No new request was
          sent.
        </p>
      ) : query.isPending || query.isFetching ? (
        <Loading />
      ) : query.error ? (
        <ErrorBox error={query.error} retry={() => query.refetch()} />
      ) : query.data!.items.length ? (
        <div className="job-list">
          {query.data!.items.map((job) => {
            const match = query.data?.assessments?.[job.id];
            return (
              <div key={job.id}>
                {match && (
                  <div className="search-match-strip">
                    {match.state === "stale"
                      ? "Previous assessment — refresh in job details"
                      : match.state === "not_calculated"
                        ? "Candidate match not calculated"
                        : match.score == null
                          ? "Insufficient professional evidence for a score"
                          : `${match.score.toFixed(1)} / 100 candidate relevance · ${label(match.eligibility)}`}{" "}
                    ·{" "}
                    <Link to={`/jobs/${job.id}#match-analysis`}>
                      Inspect evidence
                    </Link>
                  </div>
                )}
                <JobCard job={job} />
              </div>
            );
          })}
        </div>
      ) : (
        <section className="panel">
          <Empty
            title={
              active.length
                ? "No opportunities match these filters"
                : "A clear space for real opportunities"
            }
            action={
              active.length ? (
                <button
                  className="secondary"
                  onClick={() =>
                    setUrl(params.get("q") ? { q: params.get("q")! } : {})
                  }
                >
                  Keep keywords and clear other filters
                </button>
              ) : (
                <Link to="/sources">Check source health</Link>
              )
            }
          >
            {active.length
              ? "Review the applied filters above. Score filters require current assessable matches; salary filters require disclosed compatible units. Results have not been automatically broadened."
              : "No currently visible listings have been collected. Source synchronization is operated separately from this page."}
          </Empty>
        </section>
      )}
      {query.data && !error && (
        <Pagination
          page={Number(params.get("page") || 1)}
          total={query.data.total}
          change={(page) => {
            const next = new URLSearchParams(params);
            next.set("page", String(page));
            setUrl(next);
          }}
        />
      )}
      <details className="search-notes">
        <summary>How to interpret these results</summary>
        {query.data?.notices?.map((notice) => (
          <p key={notice}>{notice}</p>
        ))}
        <p>
          Matching quality has not been independently validated. A high score
          with limited evidence is not proof of suitability.
        </p>
      </details>
    </>
  );
}
