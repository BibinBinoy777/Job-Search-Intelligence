import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../../services/api-client";
import {
  dateLabel,
  Empty,
  ErrorBox,
  Field,
  label,
  Loading,
  PageHeading,
} from "../../components/ui";
import type {
  Confirmation,
  Extraction,
  Plan,
  Preview,
  Proposal,
  Resume,
} from "./types";

async function uploadFile(file: File, resumeId: string) {
  const mime = file.name.toLowerCase().endsWith(".pdf")
    ? "application/pdf"
    : "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
  let response: Response;
  try {
    response = await fetch(
      `/api/v1/resumes${resumeId ? `/${resumeId}/versions` : ""}`,
      {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": file.type || mime,
          "X-Resume-Filename": encodeURIComponent(file.name),
        },
        body: file,
      },
    );
  } catch {
    throw new Error("Cannot reach the server. Retry the upload.");
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new ApiError(
      response.status,
      data.error?.message || "Resume upload failed",
    );
  }
  return response.json() as Promise<Resume>;
}
export default function ResumesPage() {
  const client = useQueryClient();
  const [params, setParams] = useSearchParams();
  const extractionId = params.get("extraction");
  const [notice, setNotice] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const query = useQuery({
    queryKey: ["resumes"],
    queryFn: () => api<Resume[]>("/resumes"),
    refetchOnMount: "always",
  });
  const config = useQuery({
    queryKey: ["resume-config"],
    queryFn: () => api<{ max_bytes: number }>("/resumes/config"),
  });
  const upload = useMutation({
    mutationFn: ({ file, resumeId }: { file: File; resumeId: string }) =>
      uploadFile(file, resumeId),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["resumes"] });
      setNotice(
        "Private version uploaded. Extract and review proposals before changing your profile.",
      );
    },
  });
  const process = useMutation({
    mutationFn: ({
      resumeId,
      versionId,
    }: {
      resumeId: string;
      versionId: string;
    }) =>
      api<Extraction>(`/resumes/${resumeId}/process`, "POST", {
        version_id: versionId,
      }),
    onSuccess: (run) => {
      client.setQueryData(["extraction", run.id], run);
      client.invalidateQueries({ queryKey: ["resumes"] });
      setParams({ extraction: run.id });
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) =>
      api<{ status: string }>(`/resumes/${id}`, "DELETE"),
    onSuccess: (r) => {
      client.invalidateQueries({ queryKey: ["resumes"] });
      client.removeQueries({ queryKey: ["extraction"] });
      client.removeQueries({ queryKey: ["resume-preview"] });
      setParams({});
      setDeleting(null);
      setNotice(
        r.status === "deleted"
          ? "Resume files, versions, extracted text and evidence deleted. Confirmed profile information was retained."
          : "Deletion is pending. Retry deletion to finish private-file cleanup.",
      );
    },
  });
  if (query.error instanceof ApiError && query.error.status === 404)
    return (
      <Empty
        title="Start with your candidate profile"
        action={
          <Link className="primary" to="/profile">
            Create profile
          </Link>
        }
      >
        Resume ownership uses your existing profile. No extracted qualification
        is applied automatically.
      </Empty>
    );
  return (
    <>
      <PageHeading
        eyebrow="YOUR QUALIFICATIONS, REVIEWED BY YOU"
        title="Resume intelligence."
        description="Upload privately, inspect source evidence, and explicitly confirm the facts you want in your profile."
      />
      <div className="discovery-notice">
        PDF and DOCX ·{" "}
        {((config.data?.max_bytes || 5242880) / 1048576).toFixed(0)} MiB maximum
        · Local deterministic extraction · No external AI, OCR or configured
        malware scanning.
      </div>
      <section className="panel form-panel">
        <h2>Upload a private version</h2>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const data = new FormData(e.currentTarget);
            if (!file?.size) return;
            if (config.data && file.size > config.data.max_bytes) {
              setNotice("File exceeds the configured maximum size.");
              return;
            }
            setNotice("");
            upload.mutate({
              file,
              resumeId: String(data.get("resume_id") || ""),
            });
          }}
        >
          <div className="form-grid">
            <Field
              label="Resume file"
              hint="PDF with selectable text or DOCX. A scanned PDF requires a separate OCR step that this app does not perform."
            >
              <input
                name="resume_file"
                type="file"
                accept=".pdf,.docx"
                required
                onChange={(e) => setFile(e.target.files?.[0] || null)}
              />
            </Field>
            <Field label="Version of">
              <select name="resume_id">
                <option value="">A new resume document</option>
                {query.data
                  ?.filter((r) => r.status !== "deletion_pending")
                  .map((r) => (
                    <option value={r.id} key={r.id}>
                      {r.name} · next version {r.version_count + 1}
                    </option>
                  ))}
              </select>
            </Field>
          </div>
          <button className="primary" disabled={upload.isPending}>
            {upload.isPending
              ? "Validating and uploading…"
              : "Upload private resume"}
          </button>
        </form>
        {upload.error && <ErrorBox error={upload.error} />}
      </section>
      {notice && <p role="status">{notice}</p>}
      {process.isPending && (
        <p role="status">
          Extracting in a bounded parser process. Your profile remains
          unchanged.
        </p>
      )}
      {process.error && <ErrorBox error={process.error} />}
      {remove.error && <ErrorBox error={remove.error} />}
      {query.isPending ? (
        <Loading />
      ) : query.error ? (
        <ErrorBox error={query.error} retry={() => query.refetch()} />
      ) : query.data!.length ? (
        <section className="resume-library">
          {query.data!.map((resume) => (
            <article className="panel form-panel" key={resume.id}>
              <div className="section-heading">
                <div>
                  <h2>{resume.name}</h2>
                  <p>
                    {resume.version_count} version(s) · {label(resume.status)}
                  </p>
                </div>
                <button
                  className="text-button"
                  disabled={remove.isPending}
                  onClick={() => setDeleting(resume.id)}
                >
                  {resume.status === "deletion_pending"
                    ? "Retry deletion"
                    : "Delete resume"}
                </button>
              </div>
              {deleting === resume.id && (
                <div className="source-warning">
                  <p>
                    Delete every private file version, extraction and evidence
                    record for this resume? Previously confirmed profile
                    information remains.
                  </p>
                  <button
                    className="secondary"
                    disabled={remove.isPending}
                    onClick={() => remove.mutate(resume.id)}
                  >
                    {remove.isPending ? "Deleting…" : "Confirm resume deletion"}
                  </button>
                  <button
                    className="text-button"
                    onClick={() => setDeleting(null)}
                  >
                    Cancel deletion
                  </button>
                </div>
              )}
              <ul className="resume-versions">
                {resume.versions.map((version) => (
                  <li key={version.id}>
                    <div>
                      <strong>
                        Version {version.number} · {version.filename}
                      </strong>
                      <p>
                        {dateLabel(version.created_at)} ·{" "}
                        {version.detected_type.toUpperCase()} ·{" "}
                        {(version.size_bytes / 1024).toFixed(1)} KiB ·{" "}
                        {label(version.scan_status)}
                        {" · "}
                        {version.extraction_status
                          ? label(version.extraction_status)
                          : "Not extracted"}
                      </p>
                    </div>
                    <a
                      className="text-button"
                      href={`/api/v1/resumes/${resume.id}/versions/${version.id}/download`}
                    >
                      Download version {version.number}
                    </a>
                    {version.extraction_id && (
                      <button
                        className="text-button"
                        disabled={resume.status === "deletion_pending"}
                        onClick={() =>
                          setParams({ extraction: version.extraction_id! })
                        }
                      >
                        Review version {version.number}
                      </button>
                    )}
                    <button
                      className="secondary"
                      disabled={
                        process.isPending ||
                        resume.status === "deletion_pending"
                      }
                      onClick={() =>
                        process.mutate({
                          resumeId: resume.id,
                          versionId: version.id,
                        })
                      }
                    >
                      Extract version {version.number}
                    </button>
                  </li>
                ))}
              </ul>
              {resume.latest_extraction_id && (
                <button
                  className="text-button"
                  onClick={() =>
                    setParams({ extraction: resume.latest_extraction_id! })
                  }
                >
                  Open latest extraction
                </button>
              )}
            </article>
          ))}
        </section>
      ) : (
        <Empty title="No resumes uploaded">
          Your profile can still be maintained manually. Uploading a resume is
          optional.
        </Empty>
      )}
      {extractionId && <ReviewPanel key={extractionId} id={extractionId} />}
    </>
  );
}

const fields: Record<string, string[]> = {
  skill: ["name"],
  experience: [
    "employer",
    "title",
    "start_date",
    "end_date",
    "is_current",
    "responsibilities",
    "achievements",
    "technologies",
  ],
  education: [
    "institution",
    "qualification",
    "field_of_study",
    "start_date",
    "end_date",
    "completion_status",
  ],
  summary: ["text"],
  certification: ["profile_text"],
  project: ["profile_text"],
  language: ["profile_text"],
};
const fieldNames: Record<string, string> = {
  profile_text: "Exact text to add to profile",
  is_current: "Current-role status",
  completion_status: "Education completion",
  text: "Summary text",
  name: "Skill name",
};
function Editor({
  item,
  save,
  busy,
}: {
  item: Proposal;
  save: (decision: string, value?: Record<string, unknown>) => void;
  busy: boolean;
}) {
  const value = item.reviewed_value || item.original_value;
  return (
    <details className="resume-editor">
      <summary>Edit before accepting</summary>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          const data = new FormData(e.currentTarget);
          const edited = { ...value };
          for (const key of fields[item.category] || []) {
            const raw = String(data.get(key) || "");
            edited[key] =
              key === "technologies"
                ? raw
                    .split(",")
                    .map((v) => v.trim())
                    .filter(Boolean)
                : key === "is_current"
                  ? raw === "true"
                    ? true
                    : raw === "false"
                      ? false
                      : null
                  : raw || null;
          }
          save("edited_accepted", edited);
        }}
      >
        <div className="form-grid">
          {(fields[item.category] || []).map((key) => (
            <Field
              key={key}
              label={`${fieldNames[key] || label(key)} for ${item.id.slice(0, 8)}`}
              hint={
                key === "profile_text"
                  ? "Only this reviewed text is appended to the existing profile list. Source metadata stays in the extraction."
                  : undefined
              }
            >
              {key === "is_current" ? (
                <select
                  name={key}
                  defaultValue={value[key] == null ? "" : String(value[key])}
                >
                  <option value="">Unknown</option>
                  <option value="true">Current role</option>
                  <option value="false">Not current</option>
                </select>
              ) : key === "completion_status" ? (
                <select
                  name={key}
                  defaultValue={String(value[key] || "unknown")}
                >
                  <option value="unknown">Unknown</option>
                  <option value="in_progress">In progress</option>
                  <option value="completed">Completed (I confirm)</option>
                </select>
              ) : [
                  "text",
                  "responsibilities",
                  "achievements",
                  "profile_text",
                ].includes(key) ? (
                <textarea
                  name={key}
                  defaultValue={String(value[key] || "")}
                  maxLength={key === "profile_text" ? 170 : 10000}
                />
              ) : (
                <input
                  name={key}
                  type={key.endsWith("_date") ? "date" : "text"}
                  defaultValue={
                    Array.isArray(value[key])
                      ? (value[key] as string[]).join(", ")
                      : String(value[key] || "")
                  }
                  maxLength={
                    key === "name" ? 100 : key === "technologies" ? 1000 : 200
                  }
                />
              )}
            </Field>
          ))}
        </div>
        <button className="secondary" disabled={busy}>
          Save edited acceptance
        </button>
      </form>
    </details>
  );
}
function ReviewPanel({ id }: { id: string }) {
  const client = useQueryClient();
  const [selected, setSelected] = useState<string[]>([]);
  const [resolutions, setResolutions] = useState<Record<string, string>>({});
  const [outcome, setOutcome] = useState<Confirmation | null>(null);
  const run = useQuery({
    queryKey: ["extraction", id],
    queryFn: () => api<Extraction>(`/extractions/${id}`),
    refetchOnMount: "always",
  });
  const preview = useQuery({
    queryKey: ["resume-preview", id, run.data?.revision],
    queryFn: () => api<Preview>(`/extractions/${id}/preview`),
    enabled:
      !!run.data && ["review_required", "completed"].includes(run.data.status),
  });
  const decisions = useMutation({
    mutationFn: ({
      item,
      decision,
      value,
    }: {
      item: Proposal;
      decision: string;
      value?: Record<string, unknown>;
    }) =>
      api<Extraction>(`/extractions/${id}/review`, "POST", {
        expected_revision: run.data!.revision,
        items: [{ id: item.id, decision, ...(value ? { value } : {}) }],
      }),
    onSuccess: (next) => {
      client.setQueryData(["extraction", id], next);
      client.invalidateQueries({ queryKey: ["resume-preview", id] });
      client.invalidateQueries({ queryKey: ["resumes"] });
      setOutcome(null);
    },
  });
  const confirm = useMutation({
    mutationFn: () =>
      api<Confirmation>(`/extractions/${id}/confirm`, "POST", {
        request_key: crypto.randomUUID(),
        expected_revision: preview.data!.revision,
        expected_profile_fingerprint: preview.data!.profile_fingerprint,
        item_ids: selected,
        resolutions: Object.fromEntries(
          Object.entries(resolutions).filter(([key]) => selected.includes(key)),
        ),
      }),
    onSuccess: (result) => {
      setOutcome(result);
      setSelected([]);
      [
        "profile",
        "overview",
        "resumes",
        "extraction",
        "resume-preview",
        "matching-status",
        "matches",
        "match",
        "jobs",
        "comparison",
      ].forEach((key) => client.invalidateQueries({ queryKey: [key] }));
      if (result.matching_requires_refresh)
        window.dispatchEvent(new Event("candidate-updated"));
    },
  });
  if (run.isPending) return <Loading />;
  if (run.error)
    return <ErrorBox error={run.error} retry={() => run.refetch()} />;
  const data = run.data!;
  const eligible = data.proposals.filter(
    (p) =>
      !p.applied_at && ["accepted", "edited_accepted"].includes(p.review_state),
  );
  return (
    <section className="resume-review">
      <PageHeading
        eyebrow="PROPOSALS, NOT PROFILE FACTS"
        title="Review extracted qualifications."
        description={`Status: ${label(data.status)} · ${data.extractor_version}. Evidence belongs to the displayed version. Edited claims are candidate corrections, not new source quotations.`}
      />
      <p className="small muted">
        Version reference: {data.version_id} · Attempt {data.attempts}. Dates
        not explicitly known stay blank. Review does not apply changes.
      </p>
      {data.error_message && (
        <div role="alert" className="source-warning">
          {data.error_message} Return to the version above to retry or upload a
          corrected revision.
        </div>
      )}
      {data.proposals.length === 0 && data.status !== "failed" && (
        <Empty title="No supported qualifications identified">
          Add qualifications manually or upload a clearer, structured document.
          No profile fields were changed.
        </Empty>
      )}
      {data.proposals.map((item) => (
        <article
          className="panel form-panel resume-proposal"
          key={item.id}
          aria-label={`${label(item.category)} proposal ${String(item.original_value.name || item.original_value.title || item.original_value.qualification || "text")}`}
        >
          <div className="section-heading">
            <h3>
              {label(item.category)} ·{" "}
              {String(
                item.original_value.name ||
                  item.original_value.title ||
                  item.original_value.qualification ||
                  "Source text",
              )}
            </h3>
            <span className="badge">
              {item.applied_at
                ? "Applied to profile"
                : label(item.review_state)}
            </span>
          </div>
          <dl className="resume-values">
            {Object.entries(item.reviewed_value || item.original_value)
              .filter(
                ([key, value]) =>
                  key !== "canonical" &&
                  value !== null &&
                  value !== "" &&
                  (!Array.isArray(value) || value.length),
              )
              .map(([key, value]) => (
                <div key={key}>
                  <dt>{fieldNames[key] || label(key)}</dt>
                  <dd>
                    {Array.isArray(value)
                      ? value.join(", ")
                      : typeof value === "boolean"
                        ? value
                          ? "Yes"
                          : "No"
                        : String(value)}
                  </dd>
                </div>
              ))}
          </dl>
          <blockquote>
            <p>{item.evidence.excerpt}</p>
            <footer>
              {item.evidence.page
                ? `PDF page ${item.evidence.page}`
                : `DOCX ${item.evidence.part || "paragraph"}`}{" "}
              · {label(item.evidence.section)} · Exact extracted-text span
            </footer>
          </blockquote>
          {item.warnings.map((w) => (
            <p className="small muted" key={w}>
              {w}
            </p>
          ))}
          {!item.applied_at && (
            <>
              <div className="resume-actions">
                <button
                  className="secondary"
                  disabled={decisions.isPending}
                  onClick={() =>
                    decisions.mutate({ item, decision: "accepted" })
                  }
                >
                  Accept proposal
                </button>
                <button
                  className="text-button"
                  disabled={decisions.isPending}
                  onClick={() =>
                    decisions.mutate({ item, decision: "rejected" })
                  }
                >
                  Reject proposal
                </button>
                <button
                  className="text-button"
                  disabled={decisions.isPending}
                  onClick={() =>
                    decisions.mutate({ item, decision: "pending" })
                  }
                >
                  Leave pending
                </button>
                <button
                  className="text-button"
                  disabled={decisions.isPending}
                  onClick={() =>
                    decisions.mutate({ item, decision: "needs_clarification" })
                  }
                >
                  Needs clarification
                </button>
              </div>
              <Editor
                item={item}
                busy={decisions.isPending}
                save={(decision, value) =>
                  decisions.mutate({ item, decision, value })
                }
              />
            </>
          )}
        </article>
      ))}
      {decisions.error && <ErrorBox error={decisions.error} />}
      {preview.error && (
        <ErrorBox error={preview.error} retry={() => preview.refetch()} />
      )}
      {preview.data && (
        <section className="panel form-panel">
          <h2>Preview and explicitly confirm</h2>
          <p>
            Only accepted items you select below can change your profile.
            Existing records are preserved; conflicts need an explicit choice.
          </p>
          {eligible.map((item) => {
            const plan = preview.data!.items.find((p) => p.id === item.id) as
              Plan | undefined;
            return (
              <div key={item.id} className="resume-confirm-item">
                <label>
                  <input
                    type="checkbox"
                    checked={selected.includes(item.id)}
                    disabled={plan?.action === "invalid_fields"}
                    onChange={(e) =>
                      setSelected(
                        e.target.checked
                          ? [...selected, item.id]
                          : selected.filter((key) => key !== item.id),
                      )
                    }
                  />{" "}
                  Apply {label(item.category)}:{" "}
                  {String(
                    item.original_value.name ||
                      item.original_value.title ||
                      item.original_value.qualification ||
                      "reviewed summary",
                  )}
                </label>
                <p>
                  {label(plan?.action)}
                  {plan?.message ? ` · ${plan.message}` : ""}
                </p>
                {plan?.value && (
                  <pre>{JSON.stringify(plan.value, null, 2)}</pre>
                )}
                {plan?.action === "conflict" && (
                  <>
                    <details>
                      <summary>Existing profile record</summary>
                      <pre>{JSON.stringify(plan.existing, null, 2)}</pre>
                    </details>
                    <Field
                      label={`Conflict resolution for ${item.id.slice(0, 8)}`}
                    >
                      <select
                        value={resolutions[item.id] || ""}
                        onChange={(e) =>
                          setResolutions({
                            ...resolutions,
                            [item.id]: e.target.value,
                          })
                        }
                      >
                        <option value="">Choose explicitly</option>
                        {plan.allowed_resolutions?.map((value) => (
                          <option key={value} value={value}>
                            {value === "skip"
                              ? "Keep existing; skip this proposal"
                              : value === "add_separate"
                                ? "Add a separate record; retain existing"
                                : "Replace my existing summary explicitly"}
                          </option>
                        ))}
                      </select>
                    </Field>
                  </>
                )}
              </div>
            );
          })}
          <p>
            {preview.data.unresolved_count} unresolved proposal(s). Unselected
            pending/rejected items are not applied.
          </p>
          <button
            className="primary"
            disabled={
              !selected.length ||
              confirm.isPending ||
              decisions.isPending ||
              preview.isFetching
            }
            onClick={() => confirm.mutate()}
          >
            {confirm.isPending
              ? "Applying selected changes…"
              : `Confirm ${selected.length} selected change(s)`}
          </button>
          {confirm.error && <ErrorBox error={confirm.error} />}
        </section>
      )}
      {outcome && (
        <div className="panel form-panel" role="status">
          <h2>Selected confirmation recorded</h2>
          <p>
            {outcome.changes.length} selected item(s) handled ·{" "}
            {outcome.unresolved_count} unresolved.
          </p>
          <ul>
            {outcome.changes.map((change) => (
              <li key={change.proposal_id}>{label(change.action)}</li>
            ))}
          </ul>
          <p>
            {outcome.matching_requires_refresh
              ? "Professional profile inputs changed. Existing matching assessments require an explicit refresh; they were not marked freshly calculated."
              : "This confirmation did not change professional matching inputs. Existing assessment states were retained."}
          </p>
          <Link className="text-button" to="/profile">
            Inspect profile
          </Link>{" "}
          ·{" "}
          <Link className="text-button" to="/recommended">
            Review and refresh recommendations
          </Link>
        </div>
      )}
    </section>
  );
}
