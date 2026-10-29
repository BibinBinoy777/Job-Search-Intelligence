import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { vi, describe, it, expect } from "vitest";
import App from "../app/App";
import JobsPage from "../features/job-discovery/Jobs";
import ProfilePage from "../features/candidate-profile/Profile";
import { api } from "../services/api-client";
import type { ReactNode } from "react";

function mount(node: ReactNode, path = "/") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>{node}</MemoryRouter>
    </QueryClientProvider>,
  );
}
function response(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
const profile = {
  id: "test-profile",
  name: "Test Candidate",
  headline: null,
  summary: null,
  qualifications: [],
  certifications: [],
  projects: [],
  skills: [],
  experience: [],
  education: [],
  preferences: null,
  updated_at: "2026-10-01T00:00:00Z",
};
const overview = {
  completion: 0,
  completed_fields: 0,
  total_fields: 8,
  saved_count: 0,
  application_count: 0,
  recent_activity: [],
  recent_applications: [],
};

describe("workspace UI with explicitly mocked HTTP", () => {
  it("shows loading while awaiting the backend", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise(() => {})),
    );
    mount(<JobsPage />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading");
  });
  it("shows an honest empty discovery state", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        response({ items: [], total: 0, page: 1, page_size: 12 }),
      ),
    );
    mount(<JobsPage />);
    expect(
      await screen.findByText("A clear space for real opportunities"),
    ).toBeInTheDocument();
    expect(screen.getAllByText(/Phase 2/).length).toBeGreaterThan(0);
  });
  it("passes search and filters to the backend", async () => {
    const fetcher = vi.fn(async (_path: string) =>
      response({ items: [], total: 0, page: 1, page_size: 12 }),
    );
    vi.stubGlobal("fetch", fetcher);
    mount(<JobsPage />);
    const user = userEvent.setup();
    await user.type(
      screen.getByRole("textbox", { name: "Search jobs" }),
      "Python",
    );
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Work arrangement" }),
      "remote",
    );
    await user.click(screen.getByRole("button", { name: "Search jobs" }));
    await waitFor(() =>
      expect(
        fetcher.mock.calls.some(
          (c) =>
            String(c[0]).includes("q=Python") &&
            String(c[0]).includes("work_arrangement=remote"),
        ),
      ).toBe(true),
    );
  });
  it("retains save failures and never claims success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_path: string, options?: RequestInit) =>
        options?.method === "PATCH"
          ? response({ error: { message: "Database unavailable" } }, 503)
          : response(profile),
      ),
    );
    mount(<ProfilePage />);
    const user = userEvent.setup();
    await screen.findByDisplayValue("Test Candidate");
    await user.click(screen.getByRole("button", { name: "Save profile" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Database unavailable",
    );
    expect(screen.queryByText("Profile saved.")).not.toBeInTheDocument();
  });
  it("saves profile fields through a validated API response", async () => {
    const fetcher = vi.fn(async (_path: string, options?: RequestInit) =>
      response(
        options?.method === "PATCH"
          ? { ...profile, headline: "AI Builder" }
          : profile,
      ),
    );
    vi.stubGlobal("fetch", fetcher);
    mount(<ProfilePage />);
    const user = userEvent.setup();
    await user.type(
      await screen.findByRole("textbox", { name: "Professional headline" }),
      "AI Builder",
    );
    await user.click(screen.getByRole("button", { name: "Save profile" }));
    expect(await screen.findByText("Profile saved.")).toBeInTheDocument();
    const write = fetcher.mock.calls.find((c) => c[1]?.method === "PATCH");
    expect(JSON.parse(String(write?.[1]?.body)).headline).toBe("AI Builder");
  });
  it("navigates from overview to saved jobs", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (path: string) =>
        response(
          path.endsWith("/auth/me")
            ? { id: "test-user", email: "test@example.com" }
            : path.endsWith("/overview")
              ? overview
              : path.endsWith("/profile")
                ? profile
                : { items: [], total: 0, page: 1, page_size: 12 },
        ),
      ),
    );
    mount(<App />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("link", { name: "Saved jobs" }));
    expect(
      await screen.findByRole("heading", {
        name: "Your shortlist, thoughtfully saved.",
      }),
    ).toBeInTheDocument();
  });
  it("shows sign-in for an unauthenticated session", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => response({ error: { message: "Sign in" } }, 401)),
    );
    mount(<App />);
    expect(
      await screen.findByRole("button", { name: "Sign in" }),
    ).toBeInTheDocument();
  });
  it("displays network errors with a retry action", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    mount(<JobsPage />);
    expect((await screen.findAllByRole("alert"))[0]).toHaveTextContent(
      "Cannot reach the server",
    );
    expect(
      screen.getAllByRole("button", { name: "Try again" }).length,
    ).toBeGreaterThan(0);
  });
  it("does not swallow API validation errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        response(
          {
            error: {
              message: "Check inputs",
              fields: [{ field: "body.name", message: "Too long" }],
            },
          },
          422,
        ),
      ),
    );
    await expect(api("/profile", "PATCH", { name: "X" })).rejects.toThrow(
      "name: Too long",
    );
  });
});
