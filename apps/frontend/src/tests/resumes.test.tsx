import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";
import ResumesPage from "../features/resumes/Resumes";

function mount(path = "/resumes") {
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
      <MemoryRouter initialEntries={[path]}>
        <ResumesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
const response = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
const version = {
  id: "v1",
  number: 1,
  filename: "TEST.pdf",
  detected_type: "pdf",
  size_bytes: 1024,
  scan_status: "not_configured",
  created_at: "2026-10-28T00:00:00Z",
};
const resume = {
  id: "r1",
  name: "TEST.pdf",
  status: "uploaded",
  version_count: 1,
  versions: [version],
  latest_extraction_id: null,
};
const proposal = {
  id: "p1",
  category: "skill",
  original_value: { name: "Python" },
  reviewed_value: null,
  review_state: "pending",
  warnings: [],
  applied_at: null,
  evidence: { excerpt: "Python", page: 2, part: "page", section: "skill" },
};
const run = {
  id: "e1",
  version_id: "v1",
  extractor_version: "resume-deterministic-1.0",
  status: "review_required",
  revision: 0,
  attempts: 1,
  proposals: [proposal],
};

describe("resume UI using explicitly mocked HTTP", () => {
  it("shows an honest empty library and format requirements", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input) =>
        response(
          String(input).endsWith("/config") ? { max_bytes: 5242880 } : [],
        ),
      ),
    );
    mount();
    expect(await screen.findByText("No resumes uploaded")).toBeVisible();
    expect(
      screen.getByText(/No external AI, OCR or configured malware scanning/),
    ).toBeVisible();
  });
  it("handles missing candidate profile", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input) =>
        String(input).endsWith("/config")
          ? response({ max_bytes: 5242880 })
          : response({ error: { message: "Profile not found" } }, 404),
      ),
    );
    mount();
    expect(
      await screen.findByText("Start with your candidate profile"),
    ).toBeVisible();
  });
  it("shows backend rejection without successful upload notice", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input, init) =>
        init?.method === "POST"
          ? response(
              { error: { message: "Malformed document. Export a fresh PDF." } },
              422,
            )
          : response(
              String(input).endsWith("/config") ? { max_bytes: 5242880 } : [],
            ),
      ),
    );
    mount();
    await screen.findByText("No resumes uploaded");
    await userEvent.upload(
      screen.getByLabelText("Resume file"),
      new File(["invalid"], "bad.pdf", { type: "application/pdf" }),
    );
    expect(
      (screen.getByLabelText("Resume file") as HTMLInputElement).files?.[0]
        .name,
    ).toBe("bad.pdf");
    fireEvent.submit(
      screen
        .getByRole("button", { name: "Upload private resume" })
        .closest("form")!,
    );
    expect(
      await screen.findByText("Malformed document. Export a fresh PDF."),
    ).toBeVisible();
    expect(
      screen.queryByText(/Private version uploaded/),
    ).not.toBeInTheDocument();
  });
  it("requires a second deliberate deletion action", async () => {
    const fetch = vi.fn(async (input, init) =>
      init?.method === "DELETE"
        ? response({ status: "deleted" })
        : response(
            String(input).endsWith("/config")
              ? { max_bytes: 5242880 }
              : [resume],
          ),
    );
    vi.stubGlobal("fetch", fetch);
    mount();
    await userEvent.click(
      await screen.findByRole("button", { name: "Delete resume" }),
    );
    expect(fetch.mock.calls.some(([, init]) => init?.method === "DELETE")).toBe(
      false,
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Confirm resume deletion" }),
    );
    await waitFor(() =>
      expect(
        fetch.mock.calls.some(([, init]) => init?.method === "DELETE"),
      ).toBe(true),
    );
  });
  it("shows exact evidence and keeps confirm disabled for pending proposals", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input) => {
        const url = String(input);
        return response(
          url.endsWith("/config")
            ? { max_bytes: 5242880 }
            : url.endsWith("/preview")
              ? { revision: 0, items: [], unresolved_count: 1 }
              : url.includes("/extractions/")
                ? run
                : [resume],
        );
      }),
    );
    mount("/resumes?extraction=e1");
    expect(await screen.findByText(/PDF page 2/)).toBeVisible();
    expect(
      await screen.findByRole("button", {
        name: "Confirm 0 selected change(s)",
      }),
    ).toBeDisabled();
    expect(screen.getByRole("button", { name: "Leave pending" })).toBeVisible();
  });
  it("review acceptance sends revision and never posts confirmation automatically", async () => {
    const fetch = vi.fn(async (input, init) => {
      const url = String(input);
      return response(
        url.endsWith("/config")
          ? { max_bytes: 5242880 }
          : url.endsWith("/review")
            ? {
                ...run,
                revision: 1,
                proposals: [{ ...proposal, review_state: "accepted" }],
              }
            : url.endsWith("/preview")
              ? {
                  revision: 1,
                  items: [
                    { id: "p1", action: "add", value: { name: "Python" } },
                  ],
                  unresolved_count: 1,
                }
              : url.includes("/extractions/")
                ? run
                : [resume],
      );
    });
    vi.stubGlobal("fetch", fetch);
    mount("/resumes?extraction=e1");
    await userEvent.click(
      await screen.findByRole("button", { name: "Accept proposal" }),
    );
    await screen.findByLabelText("Apply Skill: Python");
    const call = fetch.mock.calls.find(([input]) =>
      String(input).endsWith("/review"),
    )!;
    expect(JSON.parse(String(call[1]?.body))).toMatchObject({
      expected_revision: 0,
      items: [{ id: "p1", decision: "accepted" }],
    });
    expect(
      fetch.mock.calls.some(([input]) => String(input).endsWith("/confirm")),
    ).toBe(false);
  });
});
