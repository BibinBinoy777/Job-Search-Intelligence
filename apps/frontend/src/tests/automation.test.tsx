import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { it, expect, vi, beforeEach } from "vitest";
import NotificationsPage from "../features/automation/Notifications";
import AlertsPage from "../features/automation/Alerts";
import RemindersPage from "../features/automation/Reminders";
import { api, ApiError } from "../services/api-client";
vi.mock("../services/api-client", async (original) => ({
  ...(await original<object>()),
  api: vi.fn(),
}));
const empty = { items: [], total: 0, page: 1, page_size: 20 };
const caps = {
  preferences: {
    job_alerts: false,
    reminders: true,
    in_app: true,
    email: false,
    timezone: "Asia/Kolkata",
  },
  email_available: false,
};
function show(node: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  );
}
beforeEach(() => {
  vi.mocked(api).mockReset();
  vi.mocked(api).mockImplementation(
    async (path) =>
      (path === "/notifications/preferences" ? caps : empty) as never,
  );
});
it("shows empty notifications and unavailable email without fake success", async () => {
  show(<NotificationsPage />);
  expect(
    await screen.findByText("No notifications in this view"),
  ).toBeVisible();
  expect(screen.getByLabelText("Deliver optional email")).toBeDisabled();
  expect(await screen.findByLabelText("Enable job alerts")).not.toBeChecked();
});
it("persists explicit preferences", async () => {
  show(<NotificationsPage />);
  await screen.findByText("Delivery preferences");
  await userEvent.click(await screen.findByLabelText("Enable job alerts"));
  await userEvent.click(
    screen.getByRole("button", { name: "Save notification preferences" }),
  );
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith(
      "/notifications/preferences",
      "PUT",
      expect.objectContaining({
        job_alerts: true,
        email: false,
        timezone: "Asia/Kolkata",
      }),
    ),
  );
});
it("shows real delivery state and marks read", async () => {
  const n = {
    id: "n1",
    title: "TEST ONLY event",
    message: "TEST ONLY job",
    category: "new_listing",
    href: "/jobs/j1",
    job_id: "j1",
    application_id: null,
    read_at: null,
    in_app_status: "delivered",
    created_at: new Date().toISOString(),
    deliveries: [
      {
        id: "d1",
        channel: "in_app",
        status: "delivered",
        attempts: 1,
        error_code: null,
      },
    ],
  };
  vi.mocked(api).mockImplementation(
    async (path) =>
      (path === "/notifications/preferences"
        ? caps
        : { ...empty, items: [n], unread_count: 1 }) as never,
  );
  show(<NotificationsPage />);
  expect(await screen.findByText("TEST ONLY event")).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "Mark read" }));
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith("/notifications/n1/read", "PATCH", {
      read: true,
    }),
  );
});
it("shows notification failures with retry", async () => {
  vi.mocked(api).mockRejectedValue(new Error("TEST ONLY unavailable"));
  show(<NotificationsPage />);
  expect(
    (await screen.findAllByText("TEST ONLY unavailable")).length,
  ).toBeGreaterThan(0);
  expect(
    screen.getAllByRole("button", { name: /try again/i }).length,
  ).toBeGreaterThan(0);
});
it("alerts are explicit future-only subscriptions", async () => {
  show(<AlertsPage />);
  expect(await screen.findByText("No alert subscriptions")).toBeVisible();
  await userEvent.type(screen.getByLabelText("Alert name"), "TEST ONLY alert");
  await userEvent.click(
    screen.getByRole("button", { name: "Create alert subscription" }),
  );
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith(
      "/alerts",
      "POST",
      expect.objectContaining({
        name: "TEST ONLY alert",
        enabled: true,
        include_updates: false,
        email: false,
        criteria: {},
      }),
    ),
  );
});
it("reminders do not infer a due date and email is optional", async () => {
  show(<RemindersPage />);
  expect(await screen.findByText("No application reminders")).toBeVisible();
  expect(screen.getByLabelText("Local date and time")).toHaveValue("");
  expect(screen.getByLabelText("Also request optional email")).toBeDisabled();
  expect(screen.getByLabelText("Repeated daylight-saving time")).toHaveValue(
    "",
  );
});
it("missing candidate profile uses profile action", async () => {
  vi.mocked(api).mockRejectedValue(new ApiError(404, "Profile not found"));
  show(<AlertsPage />);
  expect(await screen.findByText("Create your profile first")).toBeVisible();
  expect(screen.getByRole("link", { name: "Create profile" })).toHaveAttribute(
    "href",
    "/profile",
  );
});
