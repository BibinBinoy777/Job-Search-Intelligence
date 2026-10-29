import { test, expect } from "@playwright/test";
import { randomBytes } from "node:crypto";
import fs from "node:fs";
import path from "node:path";

test("genuine PostgreSQL listings appear in the existing dashboard with source evidence", async ({
  page,
}) => {
  const email = `qa-phase2-${Date.now()}@example.com`;
  // Only the temporary account identifier is recorded for scoped cleanup, no password.
  fs.writeFileSync(
    path.resolve("../../../../work/phase2-qa-account.json"),
    JSON.stringify({ email }),
  );
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page
    .getByRole("button", { name: "New here? Create an account" })
    .click();
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password").fill(randomBytes(24).toString("hex"));
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await page.getByRole("link", { name: "My profile", exact: true }).click();
  await page.getByLabel("Full name").fill("Temporary QA validation");
  await page
    .getByRole("button", { name: "Create profile", exact: true })
    .click();
  await expect(page.getByText("Profile saved.", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Discover jobs", exact: true }).click();
  const first = page.locator(".job-card").first();
  await expect(first).toBeVisible();
  await expect(
    first.getByRole("link", { name: "Data: Himalayas ↗" }),
  ).toHaveAttribute(
    "href",
    /^https:\/\/himalayas\.app\/companies\/.*utm_source=api/,
  );
  await expect(first.getByText("Published: Not provided")).toBeVisible();
  await expect(first.locator(".job-dates")).not.toContainText(
    "Verified: Not verified",
  );
  await first.getByRole("button", { name: /^Save / }).click();
  await expect(first.getByRole("button", { name: /^Unsave / })).toBeVisible();
  await page.screenshot({
    path: path.resolve("../../docs/phase2-live-discovery.png"),
    fullPage: false,
  });
  await first.getByRole("link", { name: "View opportunity" }).click();
  await expect(page.getByText("Data sourced from Himalayas ↗")).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Open original vacancy" }),
  ).toHaveAttribute("href", /^https:\/\/himalayas\.app\/companies\//);
  await page
    .getByRole("button", { name: "Track application", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Added to tracker" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Applications", exact: true }).click();
  await expect(page.locator(".application-row")).toHaveCount(1);
  await page.getByRole("link", { name: "Data sources", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Himalayas", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Page limit reached; this batch succeeded.", {
      exact: false,
    }),
  ).toBeVisible();
  await page.screenshot({
    path: path.resolve("../../docs/phase2-live-sources.png"),
    fullPage: true,
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
    path: path.resolve("../../docs/phase2-live-mobile.png"),
    fullPage: true,
    animations: "disabled",
  });
  expect(errors).toEqual([]);
});
