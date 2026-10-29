import { test, expect } from "@playwright/test";
import path from "node:path";

test("Phase 4: URL filters, suggestions, comparison, owned search CRUD and original tracker", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .getByRole("button", { name: "New here? Create an account" })
    .click();
  await page
    .getByLabel("Email address")
    .fill(`search-${Date.now()}@example.com`);
  await page.getByLabel("Password").fill("Browser-search-password-827!");
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(
    page.getByRole("link", { name: "Discover jobs", exact: true }),
  ).toBeVisible();
  expect(
    (
      await page.request.post("/api/v1/profile", {
        data: { name: "TEST ONLY Search QA" },
      })
    ).status(),
  ).toBe(201);
  await page.getByRole("link", { name: "Discover jobs", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "2 opportunities", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", {
      name: "Compare TEST ONLY Python Builder",
      exact: true,
    })
    .click();
  await page
    .getByRole("button", {
      name: "Compare TEST ONLY Product Designer",
      exact: true,
    })
    .click();
  await expect(page.getByText("2 of 3 selected")).toBeVisible();
  await page.getByRole("link", { name: "Compare selected jobs" }).click();
  await expect(page.getByRole("table")).toBeVisible();
  await expect(page.getByText("Salary not provided")).toHaveCount(2);
  await page
    .getByRole("button", { name: "Save job", exact: true })
    .first()
    .click();
  await expect(
    page.getByRole("button", { name: "Unsave job", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Track application", exact: true })
    .first()
    .click();
  await expect(
    page.getByRole("button", { name: "Added to tracker", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: path.resolve("../../docs/phase4-comparison.png"),
    fullPage: true,
  });
  await page.getByRole("link", { name: "Back to discovery" }).click();
  await page
    .getByRole("textbox", { name: "Search jobs", exact: true })
    .fill("Pyth");
  await expect(
    page.getByRole("list", { name: "Suggestions from stored jobs" }),
  ).toBeVisible();
  await page
    .getByRole("list", { name: "Suggestions from stored jobs" })
    .getByRole("button")
    .first()
    .click();
  await page
    .getByRole("combobox", { name: "Work arrangement", exact: true })
    .selectOption("remote");
  await page
    .getByRole("combobox", { name: "Employment type", exact: true })
    .selectOption("full_time");
  await page
    .getByRole("combobox", { name: "Sort by", exact: true })
    .selectOption("title");
  await page.getByRole("button", { name: "Search jobs", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "1 opportunities", exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("combobox", { name: "Work arrangement", exact: true }),
  ).toHaveValue("remote");
  await page
    .getByText("Saved searches · definitions only, no automatic alerts")
    .click();
  await page
    .getByLabel("Search name", { exact: true })
    .fill("TEST ONLY Remote builder");
  await page
    .getByRole("button", { name: "Save current search", exact: true })
    .click();
  await expect(
    page.getByRole("button", {
      name: "Load TEST ONLY Remote builder",
      exact: true,
    }),
  ).toBeVisible();
  await page
    .getByLabel("Name for TEST ONLY Remote builder", { exact: true })
    .fill("TEST ONLY Renamed");
  await page.getByRole("button", { name: "Rename", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Load TEST ONLY Renamed", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Reset", exact: true }).click();
  await page
    .getByRole("button", { name: "Load TEST ONLY Renamed", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "1 opportunities", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Replace with current filters", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Delete TEST ONLY Renamed", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Load TEST ONLY Renamed", exact: true }),
  ).toHaveCount(0);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator(".sidebar")).not.toBeInViewport();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: path.resolve("../../docs/phase4-search-mobile.png"),
    fullPage: true,
    animations: "disabled",
  });
  await page
    .getByRole("button", {
      name: "Remove Work arrangement filter",
      exact: true,
    })
    .click();
  await expect(page).not.toHaveURL(/work_arrangement/);
});
