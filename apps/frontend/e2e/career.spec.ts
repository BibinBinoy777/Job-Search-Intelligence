import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import path from "node:path";

function fixtures(action: string) {
  execFileSync(
    process.env.BROWSER_TEST_PYTHON || "python",
    ["-m", "tests.career_browser_data", action],
    { cwd: path.resolve("../backend"), stdio: "pipe" },
  );
}
test.beforeAll(() => fixtures("seed"));
test.afterAll(() => fixtures("clean"));
test("Phase 6 career: profile evidence, gap-to-listing, adjacent role/path, resource labels and responsive scope", async ({
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
    .fill(`career-${Date.now()}@example.com`);
  await page.getByLabel("Password").fill("Career-browser-password-827!");
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(
    page.getByRole("link", { name: "Career intelligence", exact: true }),
  ).toBeVisible();
  expect(
    (
      await page.request.post("/api/v1/profile", {
        data: { name: "TEST ONLY Career Candidate" },
      })
    ).status(),
  ).toBe(201);
  await page.request.post("/api/v1/profile/skills", {
    data: { name: "Python" },
  });
  await page.request.post("/api/v1/profile/experience", {
    data: {
      title: "Research Assistant",
      employer: "TEST ONLY Research",
      technologies: ["Python"],
    },
  });
  await page
    .getByRole("link", { name: "Career intelligence", exact: true })
    .click();
  await page.getByLabel("Target role", { exact: true }).fill("Data analyst");
  await page.getByRole("button", { name: "Analyze this scope" }).click();
  const gap = page
    .locator(".career-gap")
    .filter({ has: page.getByRole("heading", { name: /SQL/ }) });
  await gap.getByText("Inspect SQL evidence", { exact: true }).click();
  await expect(gap.getByText("Python and SQL", { exact: true })).toBeVisible();
  await gap
    .getByRole("link", { name: "TEST ONLY Career Data Analyst", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "TEST ONLY Career Data Analyst",
      exact: true,
    }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Career intelligence", exact: true })
    .click();
  await page.getByLabel("Target role", { exact: true }).fill("Data analyst");
  await page.getByRole("button", { name: "Analyze this scope" }).click();
  await page
    .getByRole("button", {
      name: "Explore path to TEST ONLY Career API Engineer",
      exact: true,
    })
    .click();
  const paths = page.locator("#career-3");
  await expect(
    paths.getByText("Research Assistant", { exact: true }),
  ).toBeVisible();
  await expect(
    paths.getByText("inferred pathway from recorded evidence"),
  ).toBeVisible();
  await paths
    .getByText(/Qualifications, experience and credential requirements/)
    .click();
  await expect(
    paths.getByText("Certification required", { exact: true }),
  ).toBeVisible();
  const learning = page.locator("#career-4");
  await expect(
    learning.getByText(/Verified resource identity\/content/),
  ).toBeVisible();
  await expect(
    learning.getByText("Unverified learning direction", { exact: true }),
  ).toBeVisible();
  await expect(
    learning.getByRole("link", { name: "Open PostgreSQL Part I: Tutorial" }),
  ).toHaveAttribute(
    "href",
    "https://www.postgresql.org/docs/current/tutorial.html",
  );
  const market = page.locator("#career-5");
  await expect(
    market.getByText(/Literal source-supplied listing location/),
  ).toBeVisible();
  await expect(market.getByText(/not the broader labor market/)).toBeVisible();
  await page.screenshot({
    path: path.resolve("../../docs/phase6-career-desktop.png"),
    fullPage: true,
  });
  await page
    .getByRole("link", { name: "Review profile evidence", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Remove Python" }),
  ).toBeVisible();
  expect(
    (await (await page.request.get("/api/v1/profile")).json()).experience,
  ).toHaveLength(1);
  await page
    .getByRole("link", { name: "Career intelligence", exact: true })
    .click();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole("heading", { name: "Career intelligence.", exact: true }),
  ).toBeVisible();
  await page.getByLabel("Listing location").fill("Kochi");
  await page.getByRole("button", { name: "Analyze this scope" }).click();
  await expect(page.locator("#career-5").getByText(/Kochi:/)).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: path.resolve("../../docs/phase6-career-mobile.png"),
    fullPage: true,
  });
  expect(errors).toEqual([]);
});
