import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { it, expect, vi, beforeEach } from "vitest";
import AccountSecurity, {
  RecoveryPage,
} from "../features/settings/AccountSecurity";
import { api } from "../services/api-client";
vi.mock("../services/api-client", async (original) => ({
  ...(await original<object>()),
  api: vi.fn(),
}));
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
  vi.mocked(api).mockResolvedValue({ sessions: [] });
});
it("requires separate deletion review and explicit confirmation", async () => {
  show(<AccountSecurity />);
  await screen.findByRole("heading", { name: "Security and privacy." });
  expect(
    screen.queryByLabelText("Password to confirm deletion"),
  ).not.toBeInTheDocument();
  await userEvent.click(
    screen.getByRole("button", { name: "Review account deletion" }),
  );
  expect(screen.getByLabelText("Type DELETE MY ACCOUNT")).toHaveAttribute(
    "pattern",
    "DELETE MY ACCOUNT",
  );
  expect(api).not.toHaveBeenCalledWith(
    "/account/deletion/confirm",
    expect.anything(),
    expect.anything(),
  );
});
it("exports through authenticated same-origin route", () => {
  show(<AccountSecurity />);
  expect(
    screen.getByRole("link", { name: "Download my account ZIP" }),
  ).toHaveAttribute("href", "/api/v1/account/export");
});
it("revokes all sessions explicitly", async () => {
  show(<AccountSecurity />);
  await userEvent.click(
    screen.getByRole("button", { name: "Revoke all sessions and sign out" }),
  );
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith("/account/sessions", "DELETE", undefined),
  );
});
it("recovery never invents email delivery or displays a token", () => {
  show(<RecoveryPage />);
  expect(
    screen.getByText(/Recovery email delivery is not configured/),
  ).toBeVisible();
  expect(screen.getByLabelText("Recovery credential")).toHaveAttribute(
    "type",
    "password",
  );
  expect(screen.getByLabelText("Recovery credential")).toHaveValue("");
});
it("shows real account operation failures", async () => {
  vi.mocked(api).mockRejectedValue(new Error("TEST ONLY unavailable"));
  show(<AccountSecurity />);
  expect(await screen.findByText("TEST ONLY unavailable")).toBeVisible();
});
