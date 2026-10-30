import { test, expect } from "@playwright/test";
import path from "node:path";
test("Phase 8A: private export, session revocation, password change and explicit account deletion", async ({
  page,
}) => {
  test.setTimeout(120000);
  const email = `privacy-${Date.now()}@example.com`;
  const password = "TEST ONLY browser password 8872";
  await page.goto("/");
  await page
    .getByRole("button", { name: "New here? Create an account" })
    .click();
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(
    page.getByRole("link", { name: "Account security", exact: true }),
  ).toBeVisible();
  expect(
    (
      await page.request.post("/api/v1/profile", {
        data: { name: "TEST ONLY Privacy QA" },
      })
    ).status(),
  ).toBe(201);
  const fixture = path.resolve(
    "../backend/tests/fixtures/resumes/TEST-ONLY.pdf",
  );
  const { readFileSync } = await import("node:fs");
  expect(
    (
      await page.request.post("/api/v1/resumes", {
        data: readFileSync(fixture),
        headers: {
          "Content-Type": "application/pdf",
          "X-Resume-Filename": "TEST-ONLY.pdf",
        },
      })
    ).status(),
  ).toBe(201);
  await page.goto("/account");
  await expect(
    page.getByRole("heading", { name: "Security and privacy." }),
  ).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download my account ZIP" }).click();
  expect((await download).suggestedFilename()).toBe("job-search-account.zip");
  await page.getByLabel("Current password", { exact: true }).fill(password);
  await page
    .getByLabel("New password", { exact: true })
    .fill("TEST ONLY replacement password 8932");
  const changed = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/v1/account/password") &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Change password and revoke all sessions" })
    .click();
  expect((await changed).status()).toBe(200);
  expect((await page.request.get("/api/v1/auth/me")).status()).toBe(401);
  await page.goto("/");
  await page.getByLabel("Email address").fill(email);
  await page
    .getByLabel("Password", { exact: true })
    .fill("TEST ONLY replacement password 8932");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("link", { name: "Account security", exact: true }),
  ).toBeVisible();
  await page.goto("/account");
  await page.getByRole("button", { name: "Review account deletion" }).click();
  await page
    .getByLabel("Password to confirm deletion")
    .fill("TEST ONLY replacement password 8932");
  await page.getByLabel("Type DELETE MY ACCOUNT").fill("DELETE MY ACCOUNT");
  await page
    .getByRole("button", { name: "Permanently delete my account" })
    .click();
  await expect(
    page.getByRole("button", { name: "Sign in", exact: true }),
  ).toBeVisible();
  expect((await page.request.get("/api/v1/auth/me")).status()).toBe(401);
  await page
    .getByRole("button", { name: "Recover my account", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Account recovery", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText(/Recovery email delivery is not configured/),
  ).toBeVisible();
});
