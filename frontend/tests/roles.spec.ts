import { type APIRequestContext, expect, test } from "@playwright/test"
import { firstSuperuser, firstSuperuserPassword } from "./config"
import { randomEmail, randomPassword } from "./utils/random"
import { logInUser, logOutUser } from "./utils/user"

async function createRoleUser(
  request: APIRequestContext,
  role: "manager" | "member",
) {
  const apiUrl = process.env.VITE_API_URL ?? "http://localhost:8000"
  const login = await request.post(`${apiUrl}/api/v1/login/access-token`, {
    form: { username: firstSuperuser, password: firstSuperuserPassword },
  })
  expect(login.ok()).toBeTruthy()
  const { access_token } = await login.json()
  const email = randomEmail()
  const password = randomPassword()
  const response = await request.post(`${apiUrl}/api/v1/users/`, {
    headers: { Authorization: `Bearer ${access_token}` },
    data: { email, password, role },
  })
  expect(response.ok()).toBeTruthy()
  return { email, password }
}

test.use({ storageState: { cookies: [], origins: [] } })

test("Manager can read users and metrics without administrative controls", async ({
  page,
  request,
}) => {
  const user = await createRoleUser(request, "manager")
  await logInUser(page, user.email, user.password)
  await page.goto("/admin")
  await expect(page.getByRole("heading", { name: "Users" })).toBeVisible()
  await expect(page.getByRole("button", { name: "Add User" })).toHaveCount(0)
  await expect(page.locator("tbody button")).toHaveCount(0)
  await page.goto("/metrics")
  await expect(page.getByRole("heading", { name: "Metrics" })).toBeVisible()
  await expect(page.getByText("Total users")).toBeVisible()
})

test("Member direct navigation shows denial and preserves the session", async ({
  page,
  request,
}) => {
  const user = await createRoleUser(request, "member")
  await logInUser(page, user.email, user.password)
  await expect(
    page.getByRole("link", { name: "Users", exact: true }),
  ).toHaveCount(0)
  await expect(
    page.getByRole("link", { name: "Metrics", exact: true }),
  ).toHaveCount(0)
  const token = await page.evaluate(() => localStorage.getItem("access_token"))

  for (const path of ["/admin", "/metrics"]) {
    await page.goto(path)
    await expect(
      page.getByRole("heading", { name: "Access Denied" }),
    ).toBeVisible()
    expect(
      await page.evaluate(() => localStorage.getItem("access_token")),
    ).toBe(token)
  }

  await page.goto("/settings")
  await expect(
    page.getByRole("heading", { name: "User Settings" }),
  ).toBeVisible()
  await expect(page.getByRole("tab", { name: "Danger zone" })).toBeVisible()
})

test("Switching from admin to member clears administrative UI", async ({
  page,
  request,
}) => {
  const user = await createRoleUser(request, "member")
  await logInUser(page, firstSuperuser, firstSuperuserPassword)
  await page.goto("/admin")
  await expect(page.getByRole("button", { name: "Add User" })).toBeVisible()
  await logOutUser(page)
  await logInUser(page, user.email, user.password)
  await expect(
    page.getByRole("link", { name: "Users", exact: true }),
  ).toHaveCount(0)
  await page.goto("/admin")
  await expect(
    page.getByRole("heading", { name: "Access Denied" }),
  ).toBeVisible()
})

test("A forbidden API response displays denial without signing out", async ({
  page,
  request,
}) => {
  const user = await createRoleUser(request, "manager")
  await logInUser(page, user.email, user.password)
  const token = await page.evaluate(() => localStorage.getItem("access_token"))
  await page.route("**/api/v1/metrics/", (route) =>
    route.fulfill({
      status: 403,
      contentType: "application/json",
      body: JSON.stringify({
        detail: "The user doesn't have enough privileges",
      }),
    }),
  )
  await page.goto("/metrics")
  await expect(
    page.getByRole("heading", { name: "Access Denied" }),
  ).toBeVisible()
  expect(await page.evaluate(() => localStorage.getItem("access_token"))).toBe(
    token,
  )
  await page.goto("/settings")
  await expect(
    page.getByRole("heading", { name: "User Settings" }),
  ).toBeVisible()
})
