import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import path from "node:path";
function fixtures(action: string) {
  execFileSync(
    process.env.BROWSER_TEST_PYTHON || "python",
    ["-m", "tests.automation_browser_data", action],
    { cwd: path.resolve("../backend"), stdio: "pipe" },
  );
}
test.afterAll(() => fixtures("clean"));
test("Phase 7: explicit alerts, real worker dispatch, read state, reminder timezone and cancellation", async ({
  page,
}) => {
  test.setTimeout(120000);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page
    .getByRole("button", { name: "New here? Create an account" })
    .click();
  await page
    .getByLabel("Email address")
    .fill(`automation-${Date.now()}@example.com`);
  await page.getByLabel("Password").fill("Automation-browser-password-827!");
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(
    page.getByRole("link", { name: "Job alerts", exact: true }),
  ).toBeVisible();
  expect(
    (
      await page.request.post("/api/v1/profile", {
        data: { name: "TEST ONLY Automation QA" },
      })
    ).status(),
  ).toBe(201);
  await page.goto("/notifications");
  await expect(page.getByText("No notifications in this view")).toBeVisible();
  await expect(page.getByLabel("Deliver optional email")).toBeDisabled();
  await page.getByLabel("Enable job alerts").check();
  await page.getByLabel("Preferred timezone").fill("Asia/Kolkata");
  await page
    .getByRole("button", { name: "Save notification preferences" })
    .click();
  await expect(page.getByText(/Notification preferences saved/)).toBeVisible();
  await page.goto("/alerts");
  await page.getByLabel("Alert name").fill("TEST ONLY browser subscription");
  await page.getByLabel("Alert keywords").fill("automation");
  await page.getByRole("button", { name: "Create alert subscription" }).click();
  await expect(
    page.getByRole("button", { name: "Pause TEST ONLY browser subscription" }),
  ).toBeVisible();
  fixtures("ingest");
  fixtures("tick");
  await page.goto("/notifications");
  await expect(
    page.getByRole("heading", { name: "New listing observed", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("TEST ONLY Automation Browser Job", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Mark read", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Mark unread", exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("button", { name: "Mark unread", exact: true }),
  ).toBeVisible();
  fixtures("ingest");
  fixtures("tick");
  expect(
    (await (await page.request.get("/api/v1/notifications")).json()).total,
  ).toBe(1);
  const jobs = await (
    await page.request.get("/api/v1/jobs?title=TEST%20ONLY%20Python%20Builder")
  ).json();
  const app = await (
    await page.request.post("/api/v1/applications", {
      data: { job_id: jobs.items[0].id },
    })
  ).json();
  await page.goto(`/reminders?application=${app.id}`);
  await expect(page.getByLabel("Application ID")).toHaveValue(app.id);
  await page.getByLabel("Local date and time").fill("2026-01-01T10:30");
  await page.getByLabel("Reminder timezone").fill("Asia/Kolkata");
  await page
    .getByLabel("Private reminder note")
    .fill("TEST ONLY private preparation note");
  await page
    .getByRole("button", { name: "Create application reminder" })
    .click();
  await expect(
    page.getByRole("button", { name: "Complete reminder", exact: true }),
  ).toBeVisible();
  fixtures("tick");
  await page.goto("/notifications");
  await expect(
    page.getByRole("heading", { name: "Application reminder", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Open related application", exact: true })
    .click();
  await expect(
    page.getByRole("link", { name: "Schedule reminder", exact: true }),
  ).toBeVisible();
  await page.goto("/reminders");
  await page
    .getByRole("button", { name: "Complete reminder", exact: true })
    .click();
  await expect(page.getByText("Completed", { exact: true })).toBeVisible();
  await page.getByLabel("Application ID").fill(app.id);
  await page.getByLabel("Local date and time").fill("2027-01-01T10:30");
  await page
    .getByRole("button", { name: "Create application reminder" })
    .click();
  await page
    .getByRole("button", { name: "Cancel reminder", exact: true })
    .click();
  await expect(page.getByText("Cancelled", { exact: true })).toBeVisible();
  await page.goto("/alerts");
  await page
    .getByRole("button", { name: "Pause TEST ONLY browser subscription" })
    .click();
  await expect(
    page.getByRole("button", { name: "Resume TEST ONLY browser subscription" }),
  ).toBeVisible();
  expect((await page.request.get("/api/v1/automation/status")).status()).toBe(
    403,
  );
  fixtures("operator");
  await page.goto("/sources");
  await expect(
    page.getByRole("heading", { name: "Operator automation controls" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", {
      name: "Delivery history and uncertain outcomes",
    }),
  ).toBeVisible();
  const schedule = page
    .locator("form.automation-schedule")
    .filter({ hasText: "automation browser fixtures" });
  await expect(schedule.getByRole("checkbox")).not.toBeChecked();
  await schedule.getByRole("checkbox").check();
  await schedule.getByRole("button", { name: /Save .* schedule/ }).click();
  await expect(page.getByText(/Operational change recorded/)).toBeVisible();
  await expect(schedule.getByRole("checkbox")).toBeChecked();
  await schedule.getByRole("checkbox").uncheck();
  await schedule.getByRole("button", { name: /Save .* schedule/ }).click();
  await expect(schedule.getByRole("checkbox")).not.toBeChecked();
  await page.screenshot({
    path: path.resolve("../../docs/phase7-operations-desktop.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/notifications");
  await expect(
    page.getByRole("heading", { name: "Your notifications." }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: path.resolve("../../docs/phase7-notifications-mobile.png"),
    fullPage: true,
  });
  expect(errors).toEqual([]);
});
