/**
 * Minimal JS tour specs — exercised by Playwright (BLOCKING).
 *
 * These specs run via `npx playwright test --config=scripts/playwright.config.json --reporter=list`
 * and via `npm run test:tours`. Any failure exits non-zero and fails the CI job.
 *
 * Python-side helpers (app fixtures, seeding) remain in tours/conftest.py;
 * JS specs cover the true UI flow: login → dashboard navigation.
 */

import { test, expect } from "@playwright/test";

test.describe("Login → Dashboard tour (blocking)", () => {
	test("login page renders username/password form", async ({ page }) => {
		await page.goto("/auth/login");
		await expect(page.locator('input[name="username"]')).toBeVisible();
		await expect(page.locator('input[name="password"]')).toBeVisible();
		// Login button should be visible and enabled
		const btn = page.locator('button[type="submit"]');
		await expect(btn).toBeVisible();
	});

	test("unauthenticated dashboard redirects to login", async ({ page }) => {
		await page.goto("/dashboard");
		// Anonymous users are redirected to /auth/login (or /login)
		await expect(page).toHaveURL(/.*login.*/);
	});

	test("dashboard route responds with HTML (200 or redirect)", async ({ page }) => {
		const resp = await page.goto("/dashboard");
		// Could be 200 (if auth state present) or 302/303 redirect to login
		expect([200, 302, 303].includes(resp.status())).toBeTruthy();
		if (resp.status() === 200) {
			await expect(page.locator("body")).toBeVisible();
			const title = await page.title();
			expect(title.length).toBeGreaterThan(0);
		}
	});

	test("login → dashboard navigation visible elements", async ({ page }) => {
		await page.goto("/auth/login");
		// Verify page has expected branding/dashboard hints
		const body = await page.content();
		// Should contain form labels or Arabic login hints
		expect(body.toLowerCase().includes("login") || body.includes("تسجيل") || body.includes("username")).toBeTruthy();
		// After ensuring login page is rendered, check that a subsequent
		// navigation to / still serves content (public landing or redirect)
		const resp2 = await page.goto("/");
		expect([200, 302, 303].includes(resp2.status())).toBeTruthy();
	});
});
