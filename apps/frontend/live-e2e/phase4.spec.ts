import { test, expect } from "@playwright/test";
import { randomBytes } from "node:crypto";
import fs from "node:fs";
import path from "node:path";

test("Phase 4 genuine jobs: search, filters, stable pages, compare, save, saved-search and private matching", async ({
  page,
  browser,
}) => {
  const email = `qa-phase4-${Date.now()}@example.com`;
  const secondEmail = `qa-phase4-other-${Date.now()}@example.com`;
  const cleanupPath = path.resolve("../../../../work/phase4-qa-accounts.json");
  const previous = fs.existsSync(cleanupPath)
    ? JSON.parse(fs.readFileSync(cleanupPath, "utf8")).emails
    : [];
  fs.writeFileSync(
    cleanupPath,
    JSON.stringify({ emails: [...previous, email, secondEmail] }),
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
    page.getByRole("link", { name: "Discover jobs", exact: true }),
  ).toBeVisible();
  expect(
    (
      await page.request.post("/api/v1/profile", {
        data: {
          name: "TEMPORARY SYNTHETIC PHASE 4 QA",
          headline: "Software developer",
          projects: ["TEST ONLY Python workflow prototype"],
        },
      })
    ).status(),
  ).toBe(201);
  expect(
    (
      await page.request.post("/api/v1/profile/skills", {
        data: { name: "Python" },
      })
    ).status(),
  ).toBe(200);
  const initial = await (
    await page.request.get("/api/v1/jobs?page_size=12&sort=text_relevance")
  ).json();
  const allStored = await (
    await page.request.get("/api/v1/jobs?availability_scope=all&page_size=100")
  ).json();
  expect(allStored.total).toBeGreaterThanOrEqual(80);
  expect(initial.total).toBeGreaterThanOrEqual(24);
  expect(initial.total).toBeLessThanOrEqual(allStored.total);
  const jobs = initial.items;
  const refresh = await (
    await page.request.post("/api/v1/matches/refresh", { data: {} })
  ).json();
  expect(refresh.failed).toBe(0);
  const scored = await (
    await page.request.get("/api/v1/jobs?minimum_score=0&sort=candidate_match")
  ).json();
  expect(scored.total).toBeGreaterThan(0);
  expect(
    Object.values(scored.assessments).every(
      (m: any) => m.state === "current" && m.score !== null,
    ),
  ).toBe(true);
  const seen: string[] = [];
  for (let p = 1; p <= 2; p++) {
    const r = await (
      await page.request.get(`/api/v1/jobs?page=${p}&page_size=12&sort=title`)
    ).json();
    seen.push(...r.items.map((j: any) => j.id));
  }
  expect(new Set(seen).size).toBe(24);
  await page.getByRole("link", { name: "Discover jobs", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      name: `${initial.total} opportunities`,
      exact: true,
    }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Next page", exact: true }).click();
  await expect(page).toHaveURL(/page=2/);
  await page
    .getByRole("button", { name: "Previous page", exact: true })
    .click();
  await expect(page).toHaveURL(/page=1/);
  await page
    .getByRole("button", { name: `Compare ${jobs[0].title}`, exact: true })
    .first()
    .click();
  await page
    .getByRole("button", { name: `Compare ${jobs[1].title}`, exact: true })
    .first()
    .click();
  await page.getByRole("link", { name: "Compare selected jobs" }).click();
  await expect(page.getByRole("table")).toBeVisible();
  await expect(page.getByText("Data sourced from Himalayas ↗")).toHaveCount(2);
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
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: path.resolve("../../docs/phase4-live-comparison.png"),
    fullPage: true,
    animations: "disabled",
  });
  await page.getByRole("link", { name: jobs[0].title, exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Your match analysis", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Data sourced from Himalayas ↗" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Discover jobs", exact: true }).click();
  await page
    .getByRole("textbox", { name: "Search jobs", exact: true })
    .fill(jobs[0].title);
  if (jobs[0].work_arrangement)
    await page
      .getByLabel("Work arrangement", { exact: true })
      .selectOption(jobs[0].work_arrangement);
  if (jobs[0].employment_type)
    await page
      .getByLabel("Employment type", { exact: true })
      .selectOption(jobs[0].employment_type);
  await page
    .getByLabel("Sort by", { exact: true })
    .selectOption("text_relevance");
  await page.getByRole("button", { name: "Search jobs", exact: true }).click();
  await expect(
    page.getByRole("link", { name: jobs[0].title, exact: true }),
  ).toBeVisible();
  await page
    .getByText("Saved searches · definitions only, no automatic alerts")
    .click();
  await page
    .getByLabel("Search name", { exact: true })
    .fill("TEST ONLY Genuine source query");
  await page
    .getByRole("button", { name: "Save current search", exact: true })
    .click();
  await expect(
    page.getByRole("button", {
      name: "Load TEST ONLY Genuine source query",
      exact: true,
    }),
  ).toBeVisible();
  const own = (await (await page.request.get("/api/v1/saved-searches")).json())
    .items[0];
  await page.getByRole("button", { name: "Reset", exact: true }).click();
  await page
    .getByRole("button", {
      name: "Load TEST ONLY Genuine source query",
      exact: true,
    })
    .click();
  await expect(
    page.getByRole("textbox", { name: "Search jobs", exact: true }),
  ).toHaveValue(own.criteria.q);
  await expect(
    page.getByRole("link", { name: jobs[0].title, exact: true }),
  ).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: path.resolve("../../docs/phase4-live-search.png"),
    fullPage: false,
    animations: "disabled",
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator(".sidebar")).not.toBeInViewport();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: path.resolve("../../docs/phase4-live-mobile.png"),
    fullPage: true,
    animations: "disabled",
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  const other = await browser.newContext({ baseURL: "http://127.0.0.1:5173" });
  expect(
    (
      await other.request.post("/api/v1/auth/register", {
        data: { email: secondEmail, password: randomBytes(24).toString("hex") },
      })
    ).status(),
  ).toBe(201);
  expect(
    (
      await other.request.post("/api/v1/profile", {
        data: { name: "TEST ONLY Other QA" },
      })
    ).status(),
  ).toBe(201);
  expect(
    (await (await other.request.get("/api/v1/saved-searches")).json()).total,
  ).toBe(0);
  expect(
    (
      await other.request.patch(`/api/v1/saved-searches/${own.id}`, {
        data: { name: "Forbidden" },
      })
    ).status(),
  ).toBe(404);
  const otherCompare = await (
    await other.request.post("/api/v1/jobs/compare", {
      data: { job_ids: jobs.slice(0, 2).map((j: any) => j.id) },
    })
  ).json();
  expect(
    otherCompare.items.every(
      (i: any) => i.candidate_assessment.state === "not_calculated",
    ),
  ).toBe(true);
  await other.close();
  const saved = await (await page.request.get("/api/v1/saved-jobs")).json();
  expect(saved.total).toBe(1);
  const apps = await (await page.request.get("/api/v1/applications")).json();
  expect(apps.total).toBe(1);
  expect(errors).toEqual([]);
  fs.writeFileSync(
    path.resolve("../../docs/phase4-live-evidence.json"),
    JSON.stringify(
      {
        synthetic_temporary_qa_profiles: true,
        no_synthetic_jobs_inserted: true,
        genuine_job_count: allStored.total,
        current_discovery_job_count: initial.total,
        outside_current_discovery: allStored.total - initial.total,
        refresh,
        assessable_search_results: scored.total,
        stable_unique_first_two_pages: seen.length,
        compared_genuine_jobs: 2,
        saved_job_count: saved.total,
        tracked_application_count: apps.total,
        saved_search_created_and_reloaded: true,
        cross_candidate_access_rejected: true,
        no_page_errors: true,
        mobile_document_overflow: false,
      },
      null,
      2,
    ),
  );
});
