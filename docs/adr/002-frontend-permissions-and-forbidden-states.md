# ADR 002: Use frontend permissions for navigation and keep the API authoritative

Status: Accepted

## Problem

Managers need the existing Users page without its administrative controls. Members should not see links to that page or metrics, but typing a protected URL must still produce a useful result. The template redirects unauthorized navigation home and treats API `403` responses as a reason to log out, which hides the difference between an expired session and insufficient permission.

## Options

Relying only on backend errors would protect data but leave users with controls they cannot use. Scattering role comparisons throughout components would work initially, but make later changes harder to follow. Returning a separate capabilities list from the API would reduce policy duplication, at the cost of another response contract for this small permission set.

## Decision

Read the role from `/users/me` through the generated API client. Define one frontend permission map and reuse it for navigation, route guards, and user-management controls. Managers reuse the Users table with creation, editing, and deletion controls hidden. Personal settings stay available to every active role.

The API checks permissions independently on every protected request. Frontend checks improve the experience; changing browser state cannot grant backend access.

Show Access Denied for forbidden routes and API responses. Keep the session on `403`, stop retrying authorization failures, and reserve automatic logout for `401`. Clear cached user and application data when switching accounts. A disabled account also gets an explicit denial and a logout action instead of an empty page.

## Trade-offs

The small frontend map mirrors backend rules, so permission changes must update both sides. Role-focused API and browser tests check that they agree. There is no live subscription for permission changes: the UI refreshes its user data through existing query behavior and protected navigation checks, while the backend always uses the current database role. A capabilities response would be a reasonable next step if the policy grows substantially.
