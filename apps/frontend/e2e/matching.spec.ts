import { test, expect } from "@playwright/test";
import path from "node:path";

test("private evidence matching, refresh reuse, stale profile change and original job workflows", async ({
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
    .fill(`matching-${Date.now()}@example.com`);
  await page.getByLabel("Password").fill("Matching-test-password-827!");
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await page
    .getByRole("link", { name: "Recommended jobs", exact: true })
    .click();
  await expect(
    page.getByText("Your profile is the starting point"),
  ).toBeVisible();
  await page.getByRole("link", { name: "Create candidate profile" }).click();
  await page.getByLabel("Full name").fill("TEST ONLY Matching Candidate");
  await page.getByLabel("Professional headline").fill("Software developer");
  await page
    .getByRole("button", { name: "Create profile", exact: true })
    .click();
  await expect(page.getByText("Profile saved.", { exact: true })).toBeVisible();
  await page.getByLabel("Add a skill").fill("Python");
  await page.getByRole("button", { name: "Add skill", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Remove Python" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await page.getByLabel("Current country (optional)").fill("India");
  await page.getByLabel("Target job titles").fill("Software engineer");
  await page
    .getByRole("button", { name: "Save preferences", exact: true })
    .click();
  await expect(
    page.getByText("Preferences saved.", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Recommended jobs", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Refresh recommendations", exact: true })
    .click();
  await expect(
    page.getByText(/Refresh complete: 2 calculated, 0 unchanged/),
  ).toBeVisible();
  await expect(page.locator(".recommendation-item")).toHaveCount(2);
  await page
    .getByRole("button", { name: "Refresh recommendations", exact: true })
    .click();
  await expect(
    page.getByText(/Refresh complete: 0 calculated, 2 unchanged/),
  ).toBeVisible();
  const card = page
    .locator(".recommendation-item")
    .filter({ hasText: "TEST ONLY Python Builder" });
  await card
    .getByRole("link", { name: "Inspect evidence", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Your match analysis" }),
  ).toBeVisible();
  await page
    .getByText("Required skill evidence · 1/1 evidenced", { exact: true })
    .click();
  await expect(
    page.getByText("Vacancy evidence", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Your recorded evidence", { exact: true }),
  ).toBeVisible();
  await page.locator("#match-analysis").screenshot({
    path: path.resolve("../../docs/phase3-matching-explanation.png"),
  });
  await page
    .getByRole("button", { name: "Save opportunity", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Remove from saved", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Track application", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Added to tracker", exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "My profile", exact: true }).click();
  await page.getByLabel("Add a skill").fill("Postgres");
  await page.getByRole("button", { name: "Add skill", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Remove Postgres" }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Recommended jobs", exact: true })
    .click();
  await expect(
    page.getByText("2 previous assessments", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".recommendation-item")).toHaveCount(0);
  await page.getByLabel("Include previous assessments").check();
  await page
    .getByRole("button", { name: "Apply filters", exact: true })
    .click();
  await expect(
    page.getByText("Previous assessment · refresh required"),
  ).toHaveCount(2);
  await page
    .getByRole("button", { name: "Refresh recommendations", exact: true })
    .click();
  await expect(
    page.getByText(/Refresh complete: 2 calculated, 0 unchanged/),
  ).toBeVisible();
  await page.screenshot({
    path: path.resolve("../../docs/phase3-recommended.png"),
    fullPage: true,
    animations: "disabled",
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("button", { name: "Open menu" })).toBeVisible();
  await expect(page.locator(".sidebar")).toHaveCSS(
    "transform",
    "matrix(1, 0, 0, 1, -239, 0)",
  );
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: path.resolve("../../docs/phase3-recommended-mobile.png"),
    fullPage: true,
    animations: "disabled",
  });
  expect(errors).toEqual([]);
});
