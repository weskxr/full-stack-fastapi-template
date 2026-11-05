# Implementation notes

The aim was to extend the template without introducing a separate authorization framework. One role field is enough for these three roles. FastAPI dependencies handle endpoint access, while the existing ownership checks still control access to individual items.

Managers reuse the Users page as a read-only list. The metrics page shows two database counts, which gives it a real protected API endpoint without spending the timebox on charting. `/settings` remains personal account settings; the template does not have a global-settings feature.

The reasoning and alternatives are recorded in two short ADRs:

- [Role storage and API authorization](docs/adr/001-role-storage-and-api-authorization.md)
- [Frontend permissions and forbidden states](docs/adr/002-frontend-permissions-and-forbidden-states.md)

## What was checked

Setup was checked from a clean checkout with Python 3.14, PostgreSQL 18, uv, Bun, and Mailpit. Dependency installation, fresh migrations, and starting the app worked. Running the seed twice left exactly three demo accounts. All three could log in, and their user-list, metrics, and profile permissions matched the README. The separate Vite/backend workflow was checked too.

The final test runs passed 85 backend tests with 93% line coverage and 67 Chromium tests. Role flows also passed in Firefox and WebKit. Build, type, and lint checks passed. Migration checks covered existing-account backfill, invalid database roles, downgrade, and re-upgrade. Metrics and access-denied screens were inspected at desktop and mobile widths.

The extra edge-case checks were useful: they caught null profile updates returning server errors, a blank settings page after an account was disabled, and an invalid header in the existing password-recovery preview. Those cases now have regression tests. Account switching is tested without reloading the page so it exercises cache cleanup.

## What remains outside scope

Docker was unavailable locally, so the app ran with native PostgreSQL and Mailpit. Container builds and physical phones were not tested. Browser-engine tests and mobile-width checks do not replace those checks, and the coverage percentage is not a guarantee that every edge case is covered.

Denied-attempt logging and a new global-settings feature were left out. If the permission model becomes configurable, the next decision would be whether to return capabilities from the API instead of maintaining the small frontend map.

The changes are committed locally. A candidate-owned repository or PR link is still needed for submission; no upstream PR was opened.
