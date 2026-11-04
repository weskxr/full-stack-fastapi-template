# ADR 001: Store one role and enforce access with FastAPI dependencies

Status: Accepted

## Problem

The template represents access with `is_superuser`. That works for an administrator and a regular user, but cannot describe a manager who can read the user list without creating or editing users. The change also needs to preserve existing accounts and item ownership rules.

## Options

Keeping `is_superuser` alongside a new role would reduce some initial edits, but both fields would describe administrative access. Every update would need to keep them consistent. A permissions library or database-backed policy system would offer more flexibility, but this assignment has three fixed roles and a small set of protected endpoints. A single role field and a reusable dependency fit that scope.

## Decision

Store `admin`, `manager`, or `member` in one `role` column. Validate values with a Python enum and a database constraint. The migration maps existing superusers to admins and everyone else to members.

Use `require_roles(...)` on protected FastAPI endpoints. Keep resource ownership checks in the handlers that load those resources. For example, a manager can list users but can modify only their own items. Only admin endpoints accept role updates; signup and self-profile requests reject privilege fields.

Continue loading the user from the database during authentication. The JWT identifies the user; it does not supply the current role. Demoting or disabling an account therefore affects its existing tokens on the next request.

## Trade-offs

The policy remains defined in code, so changing permissions requires a deployment. This is reasonable for fixed application roles. Database authentication keeps the template's existing lookup rather than introducing token revocation machinery. If permissions become configurable per organization or resource, this approach would need revisiting. For now, a teammate can inspect the endpoint dependency and nearby ownership check to understand who has access.
