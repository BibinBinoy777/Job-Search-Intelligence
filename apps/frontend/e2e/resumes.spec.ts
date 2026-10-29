import { test, expect } from "@playwright/test";
import path from "node:path";

for (const kind of ["pdf", "docx"]) {
  test(`Phase 5 ${kind}: private versions, evidence, review, confirmation, stale matching and deletion`, async ({
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
      .fill(`resume-${kind}-${Date.now()}@example.com`);
    await page.getByLabel("Password").fill("Resume-test-password-827!");
    await page
      .getByRole("button", { name: "Create account", exact: true })
      .click();
    await expect(
      page.getByRole("link", { name: "My profile", exact: true }),
    ).toBeVisible();
    expect(
      (
        await page.request.post("/api/v1/profile", {
          data: { name: "TEST ONLY Resume QA" },
        })
      ).status(),
    ).toBe(201);
    expect(
      (
        await page.request.post("/api/v1/profile/skills", {
          data: { name: "Java" },
        })
      ).status(),
    ).toBe(200);
    expect(
      (
        await page.request.post("/api/v1/matches/refresh", { data: {} })
      ).status(),
    ).toBe(200);
    await page
      .getByRole("link", { name: "Resume intelligence", exact: true })
      .click();
    await expect(page.getByText("No resumes uploaded")).toBeVisible();
    const fixture = path.resolve(
      `../backend/tests/fixtures/resumes/TEST-ONLY.${kind}`,
    );
    await page.getByLabel("Resume file").setInputFiles(fixture);
    await page.getByRole("button", { name: "Upload private resume" }).click();
    await expect(page.getByText(/Private version uploaded/)).toBeVisible();
    await page
      .getByRole("button", { name: "Extract version 1", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Review extracted qualifications." }),
    ).toBeVisible();
    const skill = page.getByRole("article", {
      name: "Skill proposal Python",
      exact: true,
    });
    await expect(skill.locator("blockquote")).toContainText("Python");
    await skill.getByText("Edit before accepting", { exact: true }).click();
    await skill.getByLabel(/Skill name for/).fill("TypeScript");
    await skill.getByRole("button", { name: "Save edited acceptance" }).click();
    await expect(
      skill.getByText("Edited accepted", { exact: true }),
    ).toBeVisible();
    const education = page.getByRole("article", { name: /Education proposal/ });
    await education.getByRole("button", { name: "Reject proposal" }).click();
    await expect(
      education.getByText("Rejected", { exact: true }),
    ).toBeVisible();
    const project = page.getByRole("article", { name: /Project proposal/ });
    await project.getByRole("button", { name: "Leave pending" }).click();
    await expect(project.getByText("Pending", { exact: true })).toBeVisible();
    expect(
      (await (await page.request.get("/api/v1/profile")).json()).skills.map(
        (s: { name: string }) => s.name,
      ),
    ).toEqual(["Java"]);
    await page.getByLabel("Apply Skill: Python").check();
    await page
      .getByRole("button", { name: "Confirm 1 selected change(s)" })
      .click();
    await expect(
      page.getByRole("heading", { name: "Selected confirmation recorded" }),
    ).toBeVisible();
    await expect(
      page.getByText(
        /Existing matching assessments require an explicit refresh/,
      ),
    ).toBeVisible();
    const profile = await (await page.request.get("/api/v1/profile")).json();
    expect(profile.skills.map((s: { name: string }) => s.name).sort()).toEqual([
      "Java",
      "TypeScript",
    ]);
    expect(profile.education).toEqual([]);
    expect(profile.projects).toEqual([]);
    await page.screenshot({
      path: path.resolve(`../../docs/phase5-${kind}-review.png`),
      fullPage: true,
    });
    await page.getByLabel("Resume file").setInputFiles(fixture);
    await page
      .getByLabel("Version of")
      .selectOption({ label: `TEST-ONLY.${kind} · next version 2` });
    await page.getByRole("button", { name: "Upload private resume" }).click();
    await expect(
      page.getByRole("button", { name: "Extract version 2", exact: true }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "Delete resume", exact: true })
      .click();
    await page.getByRole("button", { name: "Confirm resume deletion" }).click();
    await expect(page.getByText("No resumes uploaded")).toBeVisible();
    expect(
      (await (await page.request.get("/api/v1/profile")).json()).skills,
    ).toHaveLength(2);
    expect(errors).toEqual([]);
  });
}
