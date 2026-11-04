import { redirect } from "@tanstack/react-router"
import { AxiosError } from "axios"

import { type UserPublic, type UserRole, UsersService } from "@/client"

type Permission = "users:read" | "users:manage" | "metrics:read"

const permissions: Record<UserRole, readonly Permission[]> = {
  admin: ["users:read", "users:manage", "metrics:read"],
  manager: ["users:read", "metrics:read"],
  member: [],
}

export const can = (
  user: UserPublic | null | undefined,
  permission: Permission,
) => !!user?.role && permissions[user.role].includes(permission)

export class AccessDeniedError extends Error {}

export async function requirePermission(permission: Permission) {
  try {
    const { data: user } = await UsersService.readUserMe()
    if (!can(user, permission)) {
      throw new AccessDeniedError("Access denied")
    }
  } catch (error) {
    if (error instanceof AxiosError && error.response?.status === 401) {
      localStorage.removeItem("access_token")
      throw redirect({ to: "/login" })
    }
    throw error
  }
}
