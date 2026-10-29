import { test, expect } from "@playwright/test";
import path from "node:path";

test("real PostgreSQL: candidate, preferences, search, saves, application history and reload", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page
    .getByRole("button", { name: "New here? Create an account" })
    .click();
  await page
    .getByLabel("Email address")
    .fill(`browser-${Date.now()}@example.com`);
  await page.getByLabel("Password").fill("Browser-test-password-827!");
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Your next chapter starts here." }),
  ).toBeVisible();
  await expect(page.getByText("0 of 8 profile sections added")).toBeVisible();
  await page.getByRole("link", { name: "My profile", exact: true }).click();
  await page.getByLabel("Full name").fill("Test Candidate");
  await page.getByLabel("Professional headline").fill("AI product builder");
  await page
    .getByLabel("Professional summary")
    .fill("Synthetic browser-test candidate profile.");
  await page
    .getByLabel("Projects", { exact: true })
    .fill("TEST ONLY Prototype");
  await page
    .getByRole("button", { name: "Create profile", exact: true })
    .click();
  await expect(page.getByText("Profile saved.", { exact: true })).toBeVisible();
  await page.getByLabel("Add a skill").fill("Python");
  await page.getByRole("button", { name: "Add skill", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Remove Python" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Add experience", exact: true })
    .click();
  await page
    .getByLabel("Employer or organization")
    .fill("TEST ONLY Organization");
  await page.getByLabel("Job title", { exact: true }).fill("TEST ONLY Builder");
  await page
    .getByRole("button", { name: "Save experience", exact: true })
    .click();
  await expect(
    page.getByText("TEST ONLY Builder", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Add education", exact: true })
    .click();
  await page
    .getByLabel("Institution", { exact: true })
    .fill("TEST ONLY Institute");
  await page
    .getByLabel("Qualification", { exact: true })
    .fill("TEST ONLY Degree");
  await page
    .getByRole("button", { name: "Save education", exact: true })
    .click();
  await expect(
    page.getByText("TEST ONLY Degree", { exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await page.getByLabel("Target job titles").fill("AI Builder");
  await page.getByLabel("Preferred locations").fill("Kochi");
  await page.getByLabel("Remote", { exact: true }).check();
  await page
    .getByRole("button", { name: "Save preferences", exact: true })
    .click();
  await expect(
    page.getByText("Preferences saved.", { exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Discover jobs", exact: true }).click();
  await page
    .getByRole("textbox", { name: "Search jobs", exact: true })
    .fill("Python");
  await page
    .getByRole("combobox", { name: "Work arrangement", exact: true })
    .selectOption("remote");
  await page.getByRole("button", { name: "Search jobs", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "1 opportunities", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Save TEST ONLY Python Builder", exact: true })
    .click();
  await expect(
    page.getByRole("button", {
      name: "Unsave TEST ONLY Python Builder",
      exact: true,
    }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Saved jobs", exact: true }).click();
  await page.reload();
  await expect(
    page.getByRole("link", { name: "TEST ONLY Python Builder", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "View opportunity", exact: true })
    .click();
  await expect(page.getByText("Not verified", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: "Track application", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Added to tracker", exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Applications", exact: true }).click();
  await page.getByRole("button", { name: /TEST ONLY Python Builder/ }).click();
  await page
    .getByLabel("Application status", { exact: true })
    .selectOption("applied");
  await page
    .getByLabel("Application notes", { exact: true })
    .fill("Submitted manually to test the tracker.");
  await page
    .getByRole("button", { name: "Save application", exact: true })
    .click();
  await expect(
    page.getByText("Application updated.", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Interested → Applied", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByLabel("Application notes", { exact: true }),
  ).toHaveValue("Submitted manually to test the tracker.");
  await page
    .getByLabel("Application status", { exact: true })
    .selectOption("interview");
  await page
    .getByRole("button", { name: "Save application", exact: true })
    .click();
  await expect(
    page.getByText("Applied → Interview", { exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Saved jobs", exact: true }).click();
  await page
    .getByRole("button", {
      name: "Unsave TEST ONLY Python Builder",
      exact: true,
    })
    .click();
  await expect(
    page.getByText("Nothing saved. Plenty ahead.", { exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  await expect(page.getByText("8 of 8 profile sections added")).toBeVisible();
  await page.screenshot({
    path: path.resolve("../../docs/qa-overview.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("button", { name: "Open menu" })).toBeVisible();
  await page.getByRole("button", { name: "Open menu" }).click();
  await page.getByRole("link", { name: "My profile", exact: true }).click();
  await expect(page.getByLabel("Full name")).toHaveValue("Test Candidate");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: path.resolve("../../docs/qa-mobile.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Open menu" }).click();
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Sign in", exact: true }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("real server: search empty state and authorization boundary", async ({
  page,
  request,
}) => {
  const anonymous = await request.get(
    "http://127.0.0.1:8001/api/v1/applications",
  );
  expect(anonymous.status()).toBe(401);
  await page.goto("/");
  await page
    .getByRole("button", { name: "New here? Create an account" })
    .click();
  await page
    .getByLabel("Email address")
    .fill(`empty-${Date.now()}@example.com`);
  await page.getByLabel("Password").fill("Browser-test-password-827!");
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await page.getByRole("link", { name: "Discover jobs", exact: true }).click();
  await page
    .getByRole("textbox", { name: "Search jobs" })
    .fill("a-query-with-no-results");
  await page.getByRole("button", { name: "Search jobs", exact: true }).click();
  await expect(
    page.getByText("No opportunities match these filters", { exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Data sources", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Know where your jobs come from." }),
  ).toBeVisible();
  await expect(
    page.getByText(/This is not a successful empty sync/),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Queue synchronization" }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: /TEST ONLY — failed API source/ })
    .click();
  await expect(
    page.getByText("Record ledger agrees with the run counters."),
  ).toBeVisible();
});
