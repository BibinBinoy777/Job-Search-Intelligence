import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";
import CareerPage from "../features/career/Career";
import type { Career } from "../features/career/types";

const listing = {
  id: "job1",
  title: "TEST ONLY Analyst",
  location: "Kochi",
  source_name: "TEST ONLY source",
  href: "/jobs/job1",
  availability: "manual / legacy availability not independently verified",
};
const stat = {
  key: "sql",
  name: "SQL",
  count: 1,
  required_count: 1,
  preferred_count: 0,
  denominator: 2,
  percentage: 50,
  candidate_status: "not_evidenced",
  observation_strength: "limited evidence",
  supporting_listings: [listing],
  requirements: [
    {
      job_id: "job1",
      category: "required",
      evidence: [
        {
          field: "description",
          text: "SQL required",
          origin: "deterministic",
          start: 0,
          end: 12,
        },
      ],
      extraction: "deterministic",
    },
  ],
  support_truncated: false,
};
const gap = {
  ...stat,
  priority: 1,
  priority_reason:
    "Required in 1 of 2 eligible listings; heuristic priority, not hiring probability.",
  relationship: "Investigate recorded Python overlap.",
  next_action: "Add existing evidence or plan relevant practice.",
  action_kind: "investigate_or_learn",
};
const data: Career = {
  analysis_version: "career-evidence-1.0",
  generated_at: "2026-10-28T12:00:00Z",
  input_fingerprint: "fixture",
  filters: {},
  profile_completeness: "skills_and_experience",
  candidate_skills: [
    {
      key: "python",
      name: "Python",
      status: "confirmed",
      used_for_role_overlap: true,
      sources: [{ kind: "profile_record", path: "skills/own-skill" }],
      note: "Candidate-recorded, not independently verified.",
    },
  ],
  origin_roles: ["Research Assistant"],
  market: {
    stored_listing_records: 3,
    scoped_records: 3,
    excluded_unavailable: 0,
    analyzed_records: 3,
    population_truncated: false,
    duplicate_records_excluded: 1,
    unique_scoped_listings: 2,
    relevant_listings: 2,
    listings_with_usable_requirements: 1,
    denominator_definition:
      "Distinct relevant listings, including unknown requirements.",
    relevance_basis: "Recorded skill overlap.",
    target_roles: [],
    requirement_kind: "all",
    sources: [{ id: "source1", name: "TEST ONLY source", count: 2 }],
    locations: [{ label: "Kochi", count: 2 }],
    publication_range: { earliest: null, latest: null, unknown_count: 2 },
    geography_definition: "Literal source-supplied locations.",
    limitations: ["Small sample; not the broader labor market."],
  },
  skill_statistics: [stat],
  gaps: [gap],
  roles: [
    {
      id: "role1",
      title: "TEST ONLY Analyst",
      listing_count: 2,
      overlap: ["Python"],
      missing_skills: ["SQL"],
      required_skill_count: 2,
      overlap_ratio: 0.5,
      candidate_sources: [
        { skill: "Python", status: "confirmed", references: [] },
      ],
      additional_requirements: [],
      representative_listings: [listing],
      reason: "Shared recorded Python evidence, not title similarity.",
      evidence_strength: "limited evidence",
      next_action: "Inspect actual requirements.",
      limitations: ["Not a suitability guarantee."],
    },
  ],
  transitions: [
    {
      origin: "Research Assistant",
      origin_kind: "recorded_experience",
      origin_evidence: [],
      destination_id: "role1",
      destination: "TEST ONLY Analyst",
      transferable_skills: ["Python"],
      skills_to_investigate: ["SQL"],
      additional_requirements: [],
      supporting_listings: [listing],
      next_steps: ["Inspect actual requirements."],
      evidence_strength: "inferred pathway from recorded evidence",
      limitations: ["No timeline is established."],
    },
  ],
  learning: [
    {
      skill_key: "sql",
      skill: "SQL",
      why: "Required in this sample.",
      practice: "Compare actual requirements with your work.",
      action_kind: "investigate_or_learn",
      supporting_job_ids: ["job1"],
      resources: [
        {
          title: "PostgreSQL Tutorial",
          provider: "PostgreSQL",
          url: "https://www.postgresql.org/docs/current/tutorial.html",
          verification_status: "verified",
          verified_on: "2026-10-28",
          verification_source:
            "https://www.postgresql.org/docs/current/tutorial.html",
          verification_evidence: "Official introduction checked.",
          level: "Introductory SQL; choose a relevant starting level.",
        },
        {
          title: "Investigate SQL exercises",
          provider: null,
          url: null,
          verification_status: "unverified_suggestion",
          verified_on: null,
          verification_source: null,
          verification_evidence: null,
          level: "Learning direction only.",
        },
      ],
    },
  ],
  notices: ["Unconfirmed resume proposals are not profile facts."],
};
function mount() {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter initialEntries={["/career"]}>
        <CareerPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
function respond(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("career dashboard with explicitly mocked HTTP", () => {
  it("shows loading without invented results", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise(() => {})),
    );
    mount();
    expect(screen.getByRole("status")).toHaveTextContent("Loading");
    expect(screen.queryByText("TEST ONLY Analyst")).not.toBeInTheDocument();
  });
  it("shows missing-profile workflow", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => respond({ error: { message: "Create profile" } }, 404)),
    );
    mount();
    expect(
      await screen.findByRole("link", { name: "Create candidate profile" }),
    ).toHaveAttribute("href", "/profile");
  });
  it("renders strengths, gap evidence and exact sample denominator", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => respond(data)),
    );
    mount();
    await screen.findByRole("heading", { name: "1. Your skills" });
    expect(screen.getByText("Confirmed", { exact: true })).toBeVisible();
    await userEvent.click(
      screen.getByText("Inspect SQL evidence", { exact: true }),
    );
    expect(screen.getByText("SQL required", { exact: true })).toBeVisible();
    expect(screen.getByText(/1 of 2 eligible relevant listings/)).toBeVisible();
    expect(
      screen.getByText("Not evidenced in your profile", { exact: true }),
    ).toBeVisible();
    expect(screen.getByRole("table")).toHaveAccessibleName(
      /Recognized skills in this dataset/,
    );
  });
  it("distinguishes role/path inference and verification status", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => respond(data)),
    );
    mount();
    await screen.findByText("inferred pathway from recorded evidence");
    expect(
      screen.getByText(/Verified resource identity\/content/),
    ).toBeVisible();
    expect(
      screen.getByText("Unverified learning direction", { exact: true }),
    ).toBeVisible();
    expect(
      screen.getByRole("link", { name: "Open PostgreSQL Tutorial" }),
    ).toHaveAttribute(
      "href",
      "https://www.postgresql.org/docs/current/tutorial.html",
    );
    expect(
      screen.queryByRole("link", { name: "Open Investigate SQL exercises" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("No timeline is established.")).toBeVisible();
  });
  it("submits scope filters with UTC dates and updates analysis", async () => {
    const fetch = vi.fn<typeof globalThis.fetch>(async () => respond(data));
    vi.stubGlobal("fetch", fetch);
    mount();
    await screen.findByRole("heading", { name: "1. Your skills" });
    await userEvent.type(screen.getByLabelText("Target role"), "Data analyst");
    await userEvent.type(screen.getByLabelText("Listing location"), "Kochi");
    await userEvent.selectOptions(
      screen.getByLabelText("Requirement category"),
      "required",
    );
    await userEvent.type(
      screen.getByLabelText("Published on or after"),
      "2026-10-01",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Analyze this scope" }),
    );
    await waitFor(() => expect(fetch.mock.calls.length).toBeGreaterThan(1));
    expect(
      JSON.parse(String(fetch.mock.calls.at(-1)?.[1]?.body)),
    ).toMatchObject({
      target_role: "Data analyst",
      location: "Kochi",
      requirement_kind: "required",
      published_after: "2026-10-01T00:00:00Z",
    });
  });
  it("shows honest empty and stale/partial-data notices", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        respond({
          ...data,
          candidate_skills: [],
          roles: [],
          gaps: [],
          transitions: [],
          learning: [],
          skill_statistics: [],
          market: {
            ...data.market,
            relevant_listings: 0,
            population_truncated: true,
            limitations: [
              "Stale listings excluded; this is a partial population.",
            ],
          },
        }),
      ),
    );
    mount();
    expect(
      await screen.findByText("No supported skill gaps to rank"),
    ).toBeVisible();
    expect(
      screen.getByText("Insufficient evidence for adjacent roles"),
    ).toBeVisible();
    expect(
      screen.getByText("No skill-specific learning actions yet"),
    ).toBeVisible();
    expect(
      screen.getByText(/Partial population. Narrow the filters/),
    ).toBeVisible();
  });
  it("shows recoverable API errors without fake recommendations", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        respond(
          { error: { message: "Database temporarily unavailable" } },
          503,
        ),
      ),
    );
    mount();
    expect(
      await screen.findByText("Database temporarily unavailable"),
    ).toBeVisible();
    expect(screen.queryByText("TEST ONLY Analyst")).not.toBeInTheDocument();
  });
  it("links profile and owned resume review without promoting extraction", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        respond({
          ...data,
          candidate_skills: [
            {
              key: "typescript",
              name: "TypeScript",
              status: "resume_evidenced",
              used_for_role_overlap: false,
              note: "Unconfirmed resume suggestion",
              sources: [
                {
                  kind: "unconfirmed_resume_proposal",
                  extraction_id: "own-run",
                  review_state: "pending",
                },
              ],
            },
          ],
        }),
      ),
    );
    mount();
    await userEvent.click(
      await screen.findByText("Qualification references for TypeScript"),
    );
    expect(
      screen.getByRole("link", { name: /Resume proposal/ }),
    ).toHaveAttribute("href", "/resumes?extraction=own-run");
    expect(
      screen.getByRole("link", { name: "Review profile evidence" }),
    ).toHaveAttribute("href", "/profile");
    expect(screen.getByText("Unconfirmed resume suggestion")).toBeVisible();
  });
});
