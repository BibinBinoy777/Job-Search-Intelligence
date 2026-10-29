import { test, expect } from "@playwright/test";
import { randomBytes } from "node:crypto";
import fs from "node:fs";
import path from "node:path";

test("matching genuine stored jobs with a clearly synthetic private QA profile", async ({
  page,
}) => {
  const email = `qa-phase3-${Date.now()}@example.com`;
  fs.writeFileSync(
    path.resolve("../../../../work/phase3-qa-account.json"),
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
  await expect(
    page.getByRole("link", { name: "Recommended jobs", exact: true }),
  ).toBeVisible();
  expect(
    (
      await page.request.post("/api/v1/profile", {
        data: {
          name: "TEMPORARY SYNTHETIC MATCHING QA",
          headline: "Software developer",
          summary:
            "Synthetic test profile for verifying matching behavior; not the real user’s career history.",
          projects: ["TEST ONLY Python workflow automation"],
        },
      })
    ).status(),
  ).toBe(201);
  for (const name of ["Python", "PostgreSQL", "JavaScript", "React", "SQL"]) {
    expect(
      (
        await page.request.post("/api/v1/profile/skills", { data: { name } })
      ).ok(),
    ).toBeTruthy();
  }
  expect(
    (
      await page.request.patch("/api/v1/profile/preferences", {
        data: {
          target_titles: ["Software engineer"],
          work_arrangements: ["remote"],
          employment_types: ["full_time"],
        },
      })
    ).ok(),
  ).toBeTruthy();
  const firstResponse = await page.request.post("/api/v1/matches/refresh", {
    data: {},
  });
  expect(firstResponse.ok()).toBeTruthy();
  const first = await firstResponse.json();
  expect(first.considered).toBeGreaterThan(0);
  expect(first.failed).toBe(0);
  const repeat = await (
    await page.request.post("/api/v1/matches/refresh", { data: {} })
  ).json();
  expect(repeat.calculated).toBe(0);
  expect(repeat.reused).toBe(first.considered);
  await page
    .getByRole("link", { name: "Recommended jobs", exact: true })
    .click();
  await expect(page.locator(".recommendation-item").first()).toBeVisible();
  await expect(
    page.getByText("0 previous assessments", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: path.resolve("../../docs/phase3-live-recommended.png"),
    fullPage: false,
    animations: "disabled",
  });
  await page
    .locator(".recommendation-item")
    .first()
    .getByRole("link", { name: "Inspect evidence", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Your match analysis" }),
  ).toBeVisible();
  await expect(page.getByText("Data sourced from Himalayas ↗")).toBeVisible();
  await page.locator("#match-analysis").screenshot({
    path: path.resolve("../../docs/phase3-live-analysis.png"),
    animations: "disabled",
  });
  const status = await (
    await page.request.get("/api/v1/matching/status")
  ).json();
  const scores = await (
    await page.request.get("/api/v1/matches?page_size=100")
  ).json();
  const evidence = {
    profile_kind: "explicitly synthetic temporary QA; not user qualifications",
    production_jobs_synthetic: false,
    source: "genuine persisted Himalayas records",
    ranking_version: status.ranking_version,
    first_refresh: first,
    immediate_repeat: repeat,
    available_jobs: status.available_job_count,
    current_results: status.current_results,
    returned_recommendations: scores.total,
    assessed_with_scores: scores.items.filter(
      (m: { score: number | null }) => m.score !== null,
    ).length,
    unknown_scores: scores.items.filter(
      (m: { score: number | null }) => m.score === null,
    ).length,
    no_browser_errors: errors.length === 0,
  };
  fs.writeFileSync(
    path.resolve("../../docs/phase3-live-evidence.json"),
    JSON.stringify(evidence, null, 2) + "\n",
  );
  expect(errors).toEqual([]);
});
