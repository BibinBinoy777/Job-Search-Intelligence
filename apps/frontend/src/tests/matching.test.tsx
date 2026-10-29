import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { vi, it, expect } from "vitest";
import type { ReactNode } from "react";
import Recommended from "../features/job-matching/Recommended";
import MatchAnalysis from "../features/job-matching/MatchAnalysis";

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
const status = {
  ranking_version: "test-baseline",
  profile_completeness: "insufficient",
  available_job_count: 2,
  current_results: 0,
  stale_results: 0,
  uncalculated_jobs: 2,
  all_available_jobs_current: false,
  last_refresh: null,
  max_batch: 200,
};
function response(value: unknown, statusCode = 200) {
  return new Response(JSON.stringify(value), {
    status: statusCode,
    headers: { "Content-Type": "application/json" },
  });
}

it("does not fabricate a zero score for uncalculated recommendations", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string) =>
      response(
        path.includes("/matching/status")
          ? status
          : { items: [], total: 0, page: 1, page_size: 12 },
      ),
    ),
  );
  mount(<Recommended />);
  expect(
    await screen.findByText("Start with an evidence-based refresh"),
  ).toBeInTheDocument();
  expect(screen.queryByText("0.0 / 100 relevance")).not.toBeInTheDocument();
});

it("guides an absent profile without requiring resume upload", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => response({ error: { message: "Create profile" } }, 404)),
  );
  mount(<Recommended />);
  expect(
    await screen.findByText("Your profile is the starting point"),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("link", { name: "Create candidate profile" }),
  ).toHaveAttribute("href", "/profile");
});

it("keeps refresh failures visible without claiming fresh success", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, options?: RequestInit) =>
      options?.method === "POST"
        ? response({ error: { message: "Matching unavailable" } }, 503)
        : response(
            path.includes("/matching/status")
              ? status
              : { items: [], total: 0, page: 1, page_size: 12 },
          ),
    ),
  );
  mount(<Recommended />);
  const button = await screen.findByRole("button", {
    name: "Refresh recommendations",
  });
  await userEvent.click(button);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Matching unavailable",
  );
  expect(screen.queryByText(/Refresh complete:/)).not.toBeInTheDocument();
});

it("distinguishes a partial refresh from successful complete calculation", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, options?: RequestInit) =>
      response(
        options?.method === "POST"
          ? {
              id: "test",
              status: "partial",
              calculated: 1,
              reused: 0,
              failed: 1,
              has_more: false,
              next_job_id: null,
            }
          : path.includes("/matching/status")
            ? status
            : { items: [], total: 0, page: 1, page_size: 12 },
      ),
    ),
  );
  mount(<Recommended />);
  await userEvent.click(
    await screen.findByRole("button", { name: "Refresh recommendations" }),
  );
  expect(
    await screen.findByText(/Partial refresh: 1 calculated, 1 failed/),
  ).toBeInTheDocument();
});

it("shows uncalculated pair state without inventing an explanation", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      response({
        state: "not_calculated",
        match: null,
        message: "Not calculated",
      }),
    ),
  );
  mount(<MatchAnalysis jobId="test-job" />);
  expect(await screen.findByText("Not assessed yet")).toBeInTheDocument();
  expect(screen.getByText(/No score has been calculated/)).toBeInTheDocument();
});
