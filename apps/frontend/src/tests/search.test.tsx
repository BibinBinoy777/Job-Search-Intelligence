import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  MemoryRouter,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router-dom";
import { describe, it, expect, vi } from "vitest";
import JobsPage, { JobCard } from "../features/job-discovery/Jobs";
import App from "../app/App";
import ComparisonPage, {
  ComparisonTray,
} from "../features/job-discovery/Comparison";
import {
  criteriaOf,
  criteriaUrl,
  readSearch,
} from "../features/job-discovery/search-state";
import type { Job } from "../types";

const job = {
  id: "11111111-1111-4111-8111-111111111111",
  title: "TEST ONLY Python Engineer",
  employer: "TEST ONLY Acme",
  description: "Synthetic component fixture",
  location: "Kochi",
  work_arrangement: "remote",
  employment_type: "full_time",
  status: "unknown",
  is_saved: false,
  source: { name: "TEST ONLY source" },
  salary_min: null,
  salary_max: null,
  published_at: null,
  last_verified_at: null,
} as Job;
function response(value: unknown, status = 200) {
  return new Response(status === 204 ? null : JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
function Location() {
  const loc = useLocation();
  const navigate = useNavigate();
  return (
    <>
      <output aria-label="Current URL">{loc.pathname + loc.search}</output>
      <button onClick={() => navigate(-1)}>Browser back</button>
    </>
  );
}
function mount(path = "/jobs", initialEntries = [path]) {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
          },
        })
      }
    >
      <MemoryRouter initialEntries={initialEntries}>
        <Location />
        <Routes>
          <Route path="/jobs" element={<JobsPage />} />
          <Route path="/compare" element={<ComparisonPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
function mock(items: Job[] = []) {
  const fetcher = vi.fn(async (url: string) => {
    if (url.includes("/jobs/suggestions"))
      return response({ items: [{ kind: "title", value: job.title }] });
    if (url.includes("/jobs?"))
      return response({
        items,
        total: items.length,
        page: 1,
        page_size: 12,
        assessments: {
          [job.id]: { state: "stale", score: null, eligibility: null },
        },
      });
    return response({ items: [], total: 0, page: 1, page_size: 50 });
  });
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}
describe("Phase 4 discovery with explicitly mocked HTTP", () => {
  it("does not let a slower old search overwrite newer results", async () => {
    let completeOld: ((value: Response) => void) | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.includes("/jobs?") && url.includes("q=first"))
          return new Promise<Response>((resolve) => {
            completeOld = resolve;
          });
        if (url.includes("/jobs?"))
          return Promise.resolve(
            response({
              items: [{ ...job, title: "TEST ONLY Second result" }],
              total: 1,
              page: 1,
              page_size: 12,
            }),
          );
        return Promise.resolve(response({ items: [], total: 0 }));
      }),
    );
    mount("/jobs?q=first");
    await waitFor(() => expect(completeOld).toBeDefined());
    const input = screen.getByRole("textbox", { name: "Search jobs" });
    await userEvent.clear(input);
    await userEvent.type(input, "second");
    await userEvent.click(screen.getByRole("button", { name: "Search jobs" }));
    await screen.findByRole("link", {
      name: "TEST ONLY Second result",
    });
    completeOld!(
      response({
        items: [{ ...job, title: "TEST ONLY Old result" }],
        total: 1,
        page: 1,
        page_size: 12,
      }),
    );
    await waitFor(() =>
      expect(
        screen.queryByRole("link", { name: "TEST ONLY Old result" }),
      ).not.toBeInTheDocument(),
    );
    expect(
      screen.getByRole("link", { name: "TEST ONLY Second result" }),
    ).toBeInTheDocument();
  });
  it("clears candidate caches on login while keeping the authentication observer", async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    client.setQueryData(["saved-searches"], { private: "previous account" });
    client.setQueryData(["comparison", "private"], {
      private: "previous account",
    });
    let signedIn = false;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.includes("/auth/login")) {
          signedIn = true;
          return response({ id: "next-user", email: "next@example.com" });
        }
        if (url.includes("/auth/me"))
          return response({ error: { message: "Sign in" } }, 401);
        return response({ error: { message: "Create your profile" } }, 404);
      }),
    );
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await screen.findByRole("button", { name: "Sign in" });
    await userEvent.type(
      screen.getByLabelText("Email address"),
      "next@example.com",
    );
    await userEvent.type(
      screen.getByLabelText("Password"),
      "TEST-password-827!",
    );
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await screen.findByRole("link", { name: "Discover jobs" });
    expect(signedIn).toBe(true);
    expect(client.getQueryData(["saved-searches"])).toBeUndefined();
    expect(client.getQueryData(["comparison", "private"])).toBeUndefined();
  });
  it("validates URL state and criteria round trips", () => {
    expect(readSearch(new URLSearchParams("page=-1")).error).toBeTruthy();
    expect(readSearch(new URLSearchParams("sort=unsafe")).error).toBeTruthy();
    expect(readSearch(new URLSearchParams("salary_min=1")).error).toMatch(
      /currency/,
    );
    expect(
      readSearch(new URLSearchParams("candidate_id=private")).error,
    ).toBeTruthy();
    expect(
      criteriaOf(new URLSearchParams("q=Python&page=8&minimum_score=0")),
    ).toEqual({ q: "Python", minimum_score: 0 });
    expect(
      criteriaUrl({ q: "SQL", skills: ["Python", "SQL"], title: null }).getAll(
        "skills",
      ),
    ).toEqual(["Python", "SQL"]);
  });
  it("rejects invalid filters before sending a job request", async () => {
    const fetcher = mock();
    mount("/jobs?page=0");
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid page");
    expect(fetcher.mock.calls.some(([url]) => url.includes("/jobs?"))).toBe(
      false,
    );
  });
  it("sorts and resets pagination while retaining active filters", async () => {
    const fetcher = mock();
    mount("/jobs?q=Python&page=3");
    const user = userEvent.setup();
    await user.selectOptions(
      screen.getByLabelText("Sort by"),
      "candidate_match",
    );
    await user.selectOptions(
      screen.getByLabelText("Work arrangement"),
      "remote",
    );
    await user.click(screen.getByRole("button", { name: "Search jobs" }));
    await waitFor(() =>
      expect(screen.getByLabelText("Current URL")).toHaveTextContent(
        "sort=candidate_match",
      ),
    );
    expect(screen.getByLabelText("Current URL")).not.toHaveTextContent(
      "page=3",
    );
    expect(
      fetcher.mock.calls.some(([url]) =>
        url.includes("work_arrangement=remote"),
      ),
    ).toBe(true);
    await user.click(
      screen.getByRole("button", { name: "Remove Work arrangement filter" }),
    );
    expect(screen.getByLabelText("Current URL")).not.toHaveTextContent(
      "work_arrangement",
    );
  });
  it("restores query and controls on back navigation", async () => {
    mock();
    mount("/jobs?q=SQL", ["/jobs?q=Python", "/jobs?q=SQL"]);
    await userEvent.click(screen.getByRole("button", { name: "Browser back" }));
    await waitFor(() =>
      expect(screen.getByRole("textbox", { name: "Search jobs" })).toHaveValue(
        "Python",
      ),
    );
  });
  it("debounces grounded suggestions and labels stale assessments", async () => {
    mock([job]);
    mount();
    const user = userEvent.setup();
    await user.type(
      screen.getByRole("textbox", { name: "Search jobs" }),
      "Pyth",
    );
    const list = await screen.findByRole("list", {
      name: "Suggestions from stored jobs",
    });
    await user.click(within(list).getByRole("button"));
    expect(screen.getByRole("textbox", { name: "Search jobs" })).toHaveValue(
      job.title,
    );
    expect(
      screen.getByText(/Previous assessment — refresh/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/0.0 \/ 100/)).not.toBeInTheDocument();
  });
  it("renders errors without claiming successful saves", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        response({ error: { message: "TEST ONLY rejected" } }, 503),
      ),
    );
    mount();
    expect((await screen.findAllByRole("alert")).length).toBeGreaterThan(0);
    expect(
      screen.queryByText("Saved-search change confirmed."),
    ).not.toBeInTheDocument();
  });
  it("compares source fields and explicit unknowns through the authorized API", async () => {
    const fetcher = vi.fn(async (_url: string) =>
      response({
        items: [{ job, requirements: null, candidate_assessment: null }],
      }),
    );
    vi.stubGlobal("fetch", fetcher);
    mount(`/compare?ids=${job.id}`);
    expect(await screen.findByRole("table")).toBeInTheDocument();
    expect(screen.getByText("Salary not provided")).toBeInTheDocument();
    expect(
      screen.getByText("Not calculated / create your profile"),
    ).toBeInTheDocument();
    expect(fetcher.mock.calls[0][0]).toContain("/jobs/compare");
  });
  it("selects a bounded comparison and can clear it", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => response({})),
    );
    const user = userEvent.setup();
    const client = new QueryClient();
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          {[
            job,
            { ...job, id: "2", title: "Two" },
            { ...job, id: "3", title: "Three" },
            { ...job, id: "4", title: "Four" },
          ].map((j) => (
            <JobCard key={j.id} job={j} />
          ))}
          <ComparisonTray />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await user.click(
      screen.getByRole("button", { name: `Compare ${job.title}` }),
    );
    await user.click(screen.getByRole("button", { name: "Compare Two" }));
    await user.click(screen.getByRole("button", { name: "Compare Three" }));
    expect(screen.getByRole("button", { name: "Compare Four" })).toBeDisabled();
    expect(screen.getByText("3 of 3 selected")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Clear comparison" }));
    expect(screen.queryByText("3 of 3 selected")).not.toBeInTheDocument();
  });
  it("creates, loads, renames, replaces and deletes a saved definition", async () => {
    let searches: {
      id: string;
      name: string;
      criteria: Record<string, unknown>;
    }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, options?: RequestInit) => {
        const body = options?.body ? JSON.parse(String(options.body)) : {};
        if (url.includes("/saved-searches")) {
          if (url.endsWith("/use")) return response(searches[0]);
          if (options?.method === "POST") {
            searches = [{ id: "saved-1", ...body }];
            return response(searches[0], 201);
          }
          if (options?.method === "PATCH") {
            searches = [{ ...searches[0], ...body }];
            return response(searches[0]);
          }
          if (options?.method === "DELETE") {
            searches = [];
            return response(null, 204);
          }
          return response({ items: searches, total: searches.length });
        }
        return response({ items: [], total: 0, page: 1, page_size: 12 });
      }),
    );
    mount("/jobs?q=Python");
    const user = userEvent.setup();
    await user.click(
      screen.getByText(
        "Saved searches · definitions only, no automatic alerts",
      ),
    );
    await user.type(screen.getByLabelText("Search name"), "My search");
    await user.click(
      screen.getByRole("button", { name: "Save current search" }),
    );
    await user.click(
      await screen.findByRole("button", { name: "Load My search" }),
    );
    await waitFor(() =>
      expect(screen.getByLabelText("Current URL")).toHaveTextContent(
        "q=Python",
      ),
    );
    const rename = screen.getByLabelText("Name for My search");
    await user.clear(rename);
    await user.type(rename, "Renamed");
    await user.click(screen.getByRole("button", { name: "Rename" }));
    await screen.findByRole("button", { name: "Load Renamed" });
    await user.click(
      screen.getByRole("button", { name: "Replace with current filters" }),
    );
    await user.click(screen.getByRole("button", { name: "Delete Renamed" }));
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "Load Renamed" }),
      ).not.toBeInTheDocument(),
    );
  });
});
