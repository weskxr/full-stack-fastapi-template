# Verification and scope

Verified locally on November 4, 2026 with Python 3.14, PostgreSQL 18, uv, Bun, and Mailpit.

## Setup

- Installed the frozen Python and frontend dependencies in a clean checkout containing only committed files.
- Migrated a new database, ran the demo seed twice, and confirmed exactly one admin, manager, and member.
- Started the clean checkout's API and built frontend, then exercised login, user listing, metrics, and own-profile updates for all three roles over HTTP.
- Separately verified the Vite development workflow against the local backend.
- Verified migration backfill from existing superusers, the database role constraint, downgrade, and re-upgrade.

## Checks

- 85 backend tests passed; measured application line coverage is 93%.
- 67 Chromium tests passed, including the existing signup, login, password recovery, profile, item, and admin flows.
- Role flows passed in Firefox and WebKit, including forbidden navigation, API denial, account switching, and accounts disabled after login.
- Frontend production build, TypeScript, mypy, ty, Ruff, and checks of changed frontend files passed.
- Desktop and mobile-width metrics and forbidden screens were visually inspected.

The follow-up audit added regression coverage for disabled tokens, invalid null profile updates, omitted-role updates, cross-user item mutations, privilege-field injection, and admin utilities. It fixed null updates returning server errors, blank settings for disabled accounts, and an inherited invalid HTTP header in the admin password-recovery preview.

## Limits and scope

Docker was unavailable on the verification machine, so execution used native PostgreSQL and Mailpit. Docker container builds and physical mobile devices were not tested. WebKit automation is not a claim of testing Safari on a physical iPhone. Passing tests and coverage do not establish that every possible edge case is covered.

The template has no global-settings feature; `/settings` remains personal account settings. Optional ADRs, diagrams, and denied-attempt logging were omitted to keep the assignment small. Public signup and the development-only user fixture remain member-only creation paths, as documented in the permission matrix.

Changes are committed locally. Publish them to a candidate-owned repository or PR before submitting the assignment; no upstream PR was opened.
