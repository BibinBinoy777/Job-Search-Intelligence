import { useSyncExternalStore, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../../services/api-client";
import {
  dateLabel,
  Empty,
  ErrorBox,
  label,
  Loading,
  PageHeading,
} from "../../components/ui";
import type { Job } from "../../types";
import type { Pair } from "../job-matching/types";
import { salaryLabel } from "./Jobs";
let selection: string[] = [];
const listeners = new Set<() => void>();
const subscribe = (fn: () => void) => {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
};
function select(ids: string[]) {
  selection = ids;
  listeners.forEach((fn) => fn());
}
export function useComparison() {
  return useSyncExternalStore(subscribe, () => selection);
}
export function CompareButton({ job }: { job: Job }) {
  const ids = useComparison();
  const included = ids.includes(job.id);
  return (
    <button
      type="button"
      className="text-button"
      aria-pressed={included}
      disabled={!included && ids.length >= 3}
      onClick={() =>
        select(included ? ids.filter((id) => id !== job.id) : [...ids, job.id])
      }
    >
      {included ? "Remove from comparison" : "Compare"}
      <span className="sr-only"> {job.title}</span>
    </button>
  );
}
export function ComparisonTray() {
  const ids = useComparison();
  return ids.length ? (
    <div className="comparison-tray" role="region" aria-label="Selected jobs">
      <strong>{ids.length} of 3 selected</strong>
      <Link className="primary" to={`/compare?ids=${ids.join(",")}`}>
        Compare selected jobs
      </Link>
      <button className="text-button" onClick={() => select([])}>
        Clear comparison
      </button>
    </div>
  ) : null;
}
interface Requirements {
  required_skills: { name: string }[];
  preferred_skills: { name: string }[];
  experience_requirements: { minimum: number }[];
  qualification_requirements: { level: string }[];
}
interface Compared {
  job: Job;
  requirements: Requirements | null;
  candidate_assessment: Pair | null;
}
function Actions({ job }: { job: Job }) {
  const client = useQueryClient();
  const [tracked, setTracked] = useState(false);
  const save = useMutation({
    mutationFn: () =>
      api(`/jobs/${job.id}/save`, job.is_saved ? "DELETE" : "PUT"),
    onSuccess: () => {
      ["comparison", "jobs", "saved", "overview"].forEach((k) =>
        client.invalidateQueries({ queryKey: [k] }),
      );
    },
  });
  const track = useMutation({
    mutationFn: () =>
      api("/applications", "POST", { job_id: job.id, status: "interested" }),
    onSuccess: () => {
      setTracked(true);
      client.invalidateQueries({ queryKey: ["applications"] });
      client.invalidateQueries({ queryKey: ["overview"] });
    },
  });
  return (
    <div className="compare-actions">
      <button
        className="secondary"
        disabled={save.isPending}
        onClick={() => save.mutate()}
      >
        {job.is_saved ? "Unsave job" : "Save job"}
      </button>
      <button
        className="secondary"
        disabled={track.isPending || tracked}
        onClick={() => track.mutate()}
      >
        {tracked ? "Added to tracker" : "Track application"}
      </button>
      <Link to="/applications">Open application tracker</Link>
      {save.error && <ErrorBox error={save.error} />}
      {track.error && <ErrorBox error={track.error} />}
    </div>
  );
}
export default function ComparisonPage() {
  const [params, setParams] = useSearchParams();
  const ids = (params.get("ids") || "").split(",").filter(Boolean);
  const valid =
    ids.length > 0 &&
    ids.length <= 3 &&
    new Set(ids).size === ids.length &&
    ids.every((id) => /^[\da-f]{8}(-[\da-f]{4}){3}-[\da-f]{12}$/i.test(id));
  const query = useQuery({
    queryKey: ["comparison", ids.join(",")],
    queryFn: () =>
      api<{ items: Compared[] }>("/jobs/compare", "POST", { job_ids: ids }),
    enabled: valid,
    refetchOnMount: "always",
  });
  function remove(id: string) {
    const next = ids.filter((value) => value !== id);
    select(next);
    setParams(next.length ? { ids: next.join(",") } : {});
  }
  if (!valid)
    return (
      <Empty
        title="Choose up to three jobs"
        action={<Link to="/jobs">Return to discovery</Link>}
      >
        Select distinct jobs using their Compare controls. No private candidate
        identifier belongs in this URL.
      </Empty>
    );
  const rows: [string, (item: Compared) => React.ReactNode][] = [
    [
      "Source & availability",
      ({ job }) => (
        <>
          {job.source?.name || "Source unknown"}
          <br />
          {label(job.status)} · {label(job.availability)}
          <br />
          Verified: {dateLabel(job.last_verified_at)}
          <br />
          Published: {dateLabel(job.published_at)}
          {job.source_url && (
            <a href={job.source_url} target="_blank" rel="noreferrer">
              Open original vacancy ↗
            </a>
          )}
          {job.source?.adapter_key === "himalayas" && (
            <a href="https://himalayas.app" target="_blank" rel="noreferrer">
              Data sourced from Himalayas ↗
            </a>
          )}
        </>
      ),
    ],
    [
      "Location & employment",
      ({ job }) => (
        <>
          {job.location || "Location unknown"}
          <br />
          {label(job.work_arrangement)} · {label(job.employment_type)}
          <br />
          Restrictions:{" "}
          {job.location_restrictions?.length
            ? job.location_restrictions.join(", ")
            : job.location_restrictions
              ? "Source lists no country restriction"
              : "Unknown"}
        </>
      ),
    ],
    ["Salary", ({ job }) => salaryLabel(job)],
    [
      "Experience expectations",
      ({ job, requirements }) =>
        job.experience_min != null
          ? `${job.experience_min}–${job.experience_max ?? "unspecified"} years (source field)`
          : requirements?.experience_requirements.length
            ? requirements.experience_requirements
                .map((r) => `${r.minimum}+ years (extracted; review source)`)
                .join("; ")
            : "Unknown / not identified",
    ],
    [
      "Required skills · source/extracted",
      (i) =>
        i.requirements?.required_skills.map((s) => s.name).join(", ") ||
        "Not identified / unavailable",
    ],
    [
      "Preferred skills · source/extracted",
      (i) =>
        i.requirements?.preferred_skills.map((s) => s.name).join(", ") ||
        "Not identified / unavailable",
    ],
    [
      "Qualifications",
      (i) => (
        <div className="compare-prose">
          {i.job.qualifications ||
            i.requirements?.qualification_requirements
              .map((r) => `${r.level} (extracted; review source)`)
              .join(", ") ||
            "Not provided / not identified"}
        </div>
      ),
    ],
    [
      "Responsibilities",
      (i) => (
        <div className="compare-prose">
          {i.job.responsibilities ||
            "Separate responsibilities not supplied; read the original description."}
        </div>
      ),
    ],
    [
      "Your assessment · separate from source",
      (i) => {
        const pair = i.candidate_assessment;
        const m = pair?.match;
        return !m ? (
          "Not calculated / create your profile"
        ) : pair?.state === "stale" ? (
          "Previous assessment — refresh in job details. Its score is not used here."
        ) : (
          <>
            {m.score == null
              ? "Insufficient information"
              : `${m.score.toFixed(1)} / 100 recorded relevance`}
            <br />
            {label(m.eligibility_status)}
            <br />
            Not hiring probability.{" "}
            {Math.round(m.assessment.weight_coverage * 100)}% scoring weight
            assessed.
          </>
        );
      },
    ],
    [
      "Your evidenced / not-evidenced required skills",
      (i) => {
        const pair = i.candidate_assessment;
        const skills =
          pair?.state === "current"
            ? pair.match?.assessment.skills.required
            : null;
        return skills ? (
          <>
            {skills
              .map(
                (s) =>
                  `${s.name}: ${s.candidate_evidence.length ? "evidenced" : "not evidenced; not proof of absence"}`,
              )
              .join("; ") || "No required skills identified"}
          </>
        ) : (
          "Current assessment unavailable"
        );
      },
    ],
    [
      "Your experience & preferences",
      (i) => {
        const m =
          i.candidate_assessment?.state === "current"
            ? i.candidate_assessment.match
            : null;
        return m
          ? ["experience", "location", "preferences"].map((key) => (
              <p key={key}>
                {label(key)}:{" "}
                {m.assessment.features[key]?.value == null
                  ? "Unknown"
                  : `${Math.round(m.assessment.features[key].value! * 100)}%`}{" "}
                · {label(m.assessment.features[key]?.reason)}
              </p>
            ))
          : "Unknown until current assessment";
      },
    ],
    [
      "Uncertainties",
      (i) => {
        const m =
          i.candidate_assessment?.state === "current"
            ? i.candidate_assessment.match
            : null;
        return (
          <div className="compare-prose">
            {m
              ? m.assessment.unknown_information
                  .map((u) => label(String(u.text)))
                  .join(" ")
              : "Matching unavailable. Missing fields do not establish eligibility or suitability."}
          </div>
        );
      },
    ],
  ];
  return (
    <>
      <PageHeading
        eyebrow="COMPARE WITH CONTEXT"
        title="Opportunities, side by side."
        description="Source-provided facts and your private assessments remain separate. Unknown fields stay unknown."
        action={<Link to="/jobs">Back to discovery</Link>}
      />
      <button
        className="text-button"
        onClick={() => {
          select([]);
          setParams({});
        }}
      >
        Clear comparison
      </button>
      {query.isPending || query.isFetching ? (
        <Loading />
      ) : query.error ? (
        <ErrorBox error={query.error} retry={() => query.refetch()} />
      ) : (
        <div
          className="comparison-scroll"
          tabIndex={0}
          aria-label="Job comparison; scroll horizontally on small screens"
        >
          <table className="comparison-table">
            <caption>
              Compare up to three jobs. Matching quality has not been
              independently validated.
            </caption>
            <thead>
              <tr>
                <th scope="col">Information</th>
                {query.data!.items.map(({ job }) => (
                  <th scope="col" key={job.id}>
                    <Link to={`/jobs/${job.id}`}>{job.title}</Link>
                    <p>{job.employer}</p>
                    <button
                      className="text-button"
                      onClick={() => remove(job.id)}
                    >
                      Remove<span className="sr-only"> {job.title}</span>
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map(([name, render]) => (
                <tr key={name}>
                  <th scope="row">{name}</th>
                  {query.data!.items.map((i) => (
                    <td key={i.job.id}>{render(i)}</td>
                  ))}
                </tr>
              ))}
              <tr>
                <th scope="row">Save & track</th>
                {query.data!.items.map((i) => (
                  <td key={i.job.id}>
                    <Actions job={i.job} />
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
