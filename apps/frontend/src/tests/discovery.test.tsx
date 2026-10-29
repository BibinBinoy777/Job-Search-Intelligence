import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { vi, it, expect } from "vitest";
import SourcesPage from "../features/job-discovery/Sources";
import { JobCard } from "../features/job-discovery/Jobs";
import type { Job } from "../types";
import type { ReactNode } from "react";

function mount(node: ReactNode) {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  );
}
const source = {
  id: "test-source",
  name: "TEST ONLY Himalayas",
  source_type: "api",
  enabled: true,
  adapter_key: "himalayas",
  operational_status: "failed",
  last_sync_at: "2026-10-27T10:00:00Z",
  last_success_at: null,
  error_code: "provider_unavailable",
};
const run = {
  id: "test-run",
  source_id: "test-source",
  source,
  trigger: "manual",
  status: "failed",
  created_at: "2026-10-27T10:00:00Z",
  started_at: null,
  finished_at: null,
  heartbeat_at: null,
  max_pages: 2,
  pages: 0,
  fetched: 0,
  accepted: 0,
  inserted: 0,
  updated: 0,
  unchanged: 0,
  duplicates: 0,
  rejected: 0,
  skipped: 0,
  retried: 2,
  errors: 1,
  error_code: "provider_unavailable",
  has_more: false,
  reconciled: true,
};
function mockHealth(canSync = false, configured = true) {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async (path: string, options?: RequestInit) =>
        new Response(
          JSON.stringify(
            path.includes("/automation/tasks") ||
              path.includes("/automation/deliveries")
              ? { items: [], total: 0, page: 1, page_size: 10 }
              : path.includes("/automation/status")
                ? {
                    enabled: true,
                    email_available: false,
                    last_completed_tick_at: null,
                    health_note: "TEST ONLY worker not recorded",
                    task_counts: {},
                    outbox_counts: {},
                    pending_reminders: 0,
                    due_reminders: 0,
                    retrying_source_runs: 0,
                  }
                : path.endsWith("/ingestion/sync")
                  ? { ...run, status: "queued" }
                  : path.includes("/ingestion/runs")
                    ? {
                        items: configured ? [run] : [],
                        total: configured ? 1 : 0,
                        page: 1,
                        page_size: 12,
                      }
                    : {
                        sources: configured
                          ? [
                              {
                                source,
                                latest_run: run,
                                stored_jobs: 20,
                                available_jobs: 19,
                              },
                            ]
                          : [],
                        can_sync: canSync,
                        worker_required: true,
                        probable_duplicate_pairs: 0,
                      },
          ),
          {
            status: options?.method === "POST" ? 202 : 200,
            headers: { "Content-Type": "application/json" },
          },
        ),
    ),
  );
}

it("shows actual failed source state and hides operator controls from a candidate", async () => {
  mockHealth();
  mount(<SourcesPage />);
  expect(
    await screen.findByText(/This is not a successful empty sync/),
  ).toBeInTheDocument();
  expect(screen.getByText("20", { exact: true })).toBeInTheDocument();
  expect(screen.getByText("19", { exact: true })).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Queue synchronization" }),
  ).not.toBeInTheDocument();
});

it("distinguishes an unconfigured source from a failed ingestion run", async () => {
  mockHealth(false, false);
  mount(<SourcesPage />);
  expect(
    await screen.findByText("No sources configured yet"),
  ).toBeInTheDocument();
  expect(
    await screen.findByText("No ingestion runs recorded"),
  ).toBeInTheDocument();
  expect(
    screen.queryByText(/This is not a successful empty sync/),
  ).not.toBeInTheDocument();
});

it("queues an operator request without claiming that collection succeeded", async () => {
  mockHealth(true);
  mount(<SourcesPage />);
  await userEvent.click(
    await screen.findByRole("button", { name: "Queue synchronization" }),
  );
  expect(
    await screen.findByText(
      /A worker must process it before results are available/,
    ),
  ).toBeInTheDocument();
});

it("keeps source attribution and unknown publication dates on a job card", () => {
  const job = {
    id: "test-job",
    title: "TEST ONLY Role",
    employer: "TEST ONLY Employer",
    description: "Synthetic frontend fixture.",
    source,
    source_url:
      "https://himalayas.app/companies/test-only/jobs/test-role?utm_source=api",
    status: "active",
    published_at: null,
    last_verified_at: "2026-10-27T10:00:00Z",
    source_updated_at: "2026-10-27T09:00:00Z",
    location: "India",
    work_arrangement: "remote",
    employment_type: "full_time",
    salary_min: null,
    salary_max: null,
    is_saved: false,
  } as unknown as Job;
  mount(<JobCard job={job} />);
  expect(
    screen.getByRole("link", { name: "Data: Himalayas ↗" }),
  ).toHaveAttribute("href", job.source_url);
  expect(screen.getByText("Published: Not provided")).toBeInTheDocument();
  expect(screen.getByText("Salary not provided")).toBeInTheDocument();
});

it("only changes saved UI after the save API confirms success", async () => {
  const fetcher = vi.fn(
    async () =>
      new Response(JSON.stringify({ error: { message: "Save failed" } }), {
        status: 503,
      }),
  );
  vi.stubGlobal("fetch", fetcher);
  const job = {
    id: "test-job",
    title: "TEST ONLY Role",
    employer: "TEST",
    description: "Synthetic fixture.",
    status: "unknown",
    published_at: null,
    last_verified_at: null,
    location: null,
    work_arrangement: null,
    employment_type: null,
    salary_min: null,
    salary_max: null,
    is_saved: false,
  } as unknown as Job;
  mount(<JobCard job={job} />);
  await userEvent.click(
    screen.getByRole("button", { name: "Save TEST ONLY Role" }),
  );
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent("Save failed"),
  );
  expect(
    screen.getByRole("button", { name: "Save TEST ONLY Role" }),
  ).toBeInTheDocument();
});
