import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Check, SlidersHorizontal } from "lucide-react";
import { api, ApiError } from "../../services/api-client";
import type { Preferences } from "../../types";
import {
  Empty,
  ErrorBox,
  Field,
  label,
  Loading,
  PageHeading,
  splitList,
} from "../../components/ui";

export default function SettingsPage() {
  const client = useQueryClient();
  const [saved, setSaved] = useState(false);
  const query = useQuery({
    queryKey: ["preferences"],
    queryFn: () => api<Preferences>("/profile/preferences"),
  });
  const mutation = useMutation({
    mutationFn: (data: unknown) => api("/profile/preferences", "PATCH", data),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["preferences"] });
      client.invalidateQueries({ queryKey: ["profile"] });
      client.invalidateQueries({ queryKey: ["overview"] });
      setSaved(true);
    },
  });
  if (query.isPending) return <Loading />;
  if (query.error)
    return query.error instanceof ApiError && query.error.status === 404 ? (
      <Empty
        title="Start with your candidate profile"
        action={
          <Link to="/profile" className="primary">
            Create profile
          </Link>
        }
      >
        Create a profile before adding career preferences.
      </Empty>
    ) : (
      <ErrorBox error={query.error} retry={() => query.refetch()} />
    );
  const p = query.data!;
  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaved(false);
    const f = new FormData(event.currentTarget);
    mutation.mutate({
      target_titles: splitList(String(f.get("target_titles"))),
      industries: splitList(String(f.get("industries"))),
      locations: splitList(String(f.get("locations"))),
      work_arrangements: f.getAll("work_arrangements"),
      employment_types: f.getAll("employment_types"),
      minimum_salary: f.get("minimum_salary")
        ? Number(f.get("minimum_salary"))
        : null,
      currency: f.get("currency") || null,
      career_level: f.get("career_level") || null,
      current_country: f.get("current_country") || null,
      relocation:
        f.get("relocation") === "unknown"
          ? null
          : f.get("relocation") === "yes",
    });
  }
  return (
    <>
      <PageHeading
        eyebrow="A SEARCH THAT FITS YOUR LIFE"
        title="Define your direction."
        description="Set your career preferences. Unknown is always an acceptable answer."
      />
      <section className="panel form-panel settings-panel">
        <div className="section-heading">
          <div>
            <h2>Career & search preferences</h2>
            <p>Explicit preferences for your evidence-based recommendations.</p>
          </div>
          <SlidersHorizontal size={21} />
        </div>
        <form onSubmit={submit}>
          <div className="form-grid">
            <Field
              label="Current country (optional)"
              hint="Your voluntary statement of current residence. Separate from preferred locations; this is not a work-authorization check."
            >
              <input
                name="current_country"
                maxLength={200}
                minLength={2}
                defaultValue={p.current_country || ""}
                placeholder="Full country name, e.g. India"
              />
            </Field>
            <Field label="Target job titles" hint="Separate with commas.">
              <input
                name="target_titles"
                defaultValue={p.target_titles.join(", ")}
              />
            </Field>
            <Field label="Target industries" hint="Separate with commas.">
              <input name="industries" defaultValue={p.industries.join(", ")} />
            </Field>
            <Field label="Preferred locations" hint="Separate with commas.">
              <input name="locations" defaultValue={p.locations.join(", ")} />
            </Field>
            <Field label="Career level">
              <select name="career_level" defaultValue={p.career_level || ""}>
                <option value="">Not specified</option>
                {[
                  "student",
                  "entry_level",
                  "early_career",
                  "mid_level",
                  "senior",
                  "leadership",
                ].map((x) => (
                  <option key={x} value={x}>
                    {label(x)}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <fieldset>
            <legend>Work arrangement</legend>
            <div className="checkbox-row">
              {["remote", "hybrid", "on_site"].map((x) => (
                <label key={x}>
                  <input
                    type="checkbox"
                    name="work_arrangements"
                    value={x}
                    defaultChecked={p.work_arrangements.includes(x)}
                  />
                  {label(x)}
                </label>
              ))}
            </div>
          </fieldset>
          <fieldset>
            <legend>Employment type</legend>
            <div className="checkbox-row">
              {[
                "full_time",
                "part_time",
                "contract",
                "internship",
                "temporary",
              ].map((x) => (
                <label key={x}>
                  <input
                    type="checkbox"
                    name="employment_types"
                    value={x}
                    defaultChecked={p.employment_types.includes(x)}
                  />
                  {label(x)}
                </label>
              ))}
            </div>
          </fieldset>
          <div className="form-grid">
            <Field label="Minimum annual salary expectation">
              <input
                name="minimum_salary"
                type="number"
                min="0"
                max="999999999999"
                step="0.01"
                defaultValue={p.minimum_salary ?? ""}
              />
            </Field>
            <Field
              label="Currency"
              hint="Three-letter currency code, e.g. INR or USD."
            >
              <input
                name="currency"
                defaultValue={p.currency || ""}
                pattern="[A-Z]{3}"
                maxLength={3}
              />
            </Field>
            <Field label="Open to relocation?">
              <select
                name="relocation"
                defaultValue={
                  p.relocation === null
                    ? "unknown"
                    : p.relocation
                      ? "yes"
                      : "no"
                }
              >
                <option value="unknown">Not specified</option>
                <option value="yes">Yes</option>
                <option value="no">No</option>
              </select>
            </Field>
          </div>
          {mutation.error && <ErrorBox error={mutation.error} />}
          <div className="form-actions">
            {saved && (
              <span role="status" className="success">
                <Check size={16} />
                Preferences saved.
              </span>
            )}
            <button className="primary" disabled={mutation.isPending}>
              {mutation.isPending ? "Saving…" : "Save preferences"}
            </button>
          </div>
        </form>
      </section>
      <p className="muted settings-note">
        Deterministic recommendations are available now. Alerts and resume
        uploads remain future capabilities.
      </p>
    </>
  );
}
