# Full Stack FastAPI Template

For the Ghost/Hetzner infrastructure task, see [one-command Ghost deployment](infra/ghost/README.md).

## Run the RBAC demo

Requirements: Python 3.14, [uv](https://docs.astral.sh/uv/), [Bun](https://bun.sh/), and Docker Compose for PostgreSQL 18 and Mailpit. The tracked `.env` contains local development defaults; use separate secrets for deployment.

From the repository root:

```bash
docker compose up -d --wait db mailpit
bun install --frozen-lockfile
cd backend
uv sync --frozen
uv run bash scripts/prestart.sh
uv run python -m app.seed_demo
uv run fastapi dev
```

In another terminal, from the repository root:

```bash
bun run dev
```

Open the app at <http://localhost:5173>, API docs at <http://localhost:8000/docs>, and captured email at <http://localhost:8025>. The seed command is development-only and creates missing accounts without resetting existing passwords or roles:

| Role | Email | Password |
|---|---|---|
| Admin | `FIRST_SUPERUSER` from `.env` | `FIRST_SUPERUSER_PASSWORD` from `.env` |
| Manager | `manager@example.com` | `DemoPassword123!` |
| Member | `member@example.com` | `DemoPassword123!` |

For a native PostgreSQL installation, create an empty database and set `DATABASE_URL=postgresql://USER:PASSWORD@localhost:5432/app` before running backend commands; Docker is not required in that case. Run Mailpit locally on SMTP port 1025 and HTTP port 8025 to capture emails.

## Permissions

| Action | Admin | Manager | Member |
|---|---|---|---|
| List users / view another user's profile | Yes | Yes | No |
| Create users / assign roles / update or delete other users | Yes | No | No |
| View metrics | Yes | Yes | No |
| View and update own profile / password | Yes | Yes | Yes |
| Create items | Yes | Yes | Yes |
| Read, update and delete items | All items | Own items | Own items |
| Delete own account | No | Yes | Yes |
| Test email / preview password-recovery email | Yes | No | No |

Public signup always creates a member. Signup and self-profile updates reject role and privilege fields. The development-only `/api/v1/private/users/` test helper also creates only members and is not registered outside development. `/settings` contains personal account settings available to every role; this template has no global-settings feature. Managers get a read-only Users page at `/admin` and can open `/metrics`.

## Authorization approach

The database stores a single `role` (`admin`, `manager`, or `member`) validated by the Python enum and a database check constraint. The migration converts existing superusers to admins and other users to members. Only admin user-management endpoints accept role changes; public signup and self-service profile schemas do not. Admin item access and the existing prohibition on admin self-deletion are preserved.

FastAPI dependencies enforce endpoint access through `require_roles(...)`; ownership checks remain next to the item/profile operations. Authentication loads the current user from the database on every request, so changing a role immediately affects existing tokens. Invalid or missing bearer credentials return `401`; authenticated users lacking permission receive `403`. A small dependency fits the existing architecture without a policy engine or additional permissions tables.

The frontend learns the role from `/users/me` through the generated OpenAPI client. A single frontend permission map controls route access, sidebar links, and user-management controls. Direct unauthorized navigation and API permission failures show a friendly Access Denied message without signing the user out. Backend checks remain authoritative; query caches are cleared when changing accounts. The frontend map intentionally mirrors the small backend policy and is covered by role-focused tests.

The alternatives and trade-offs are recorded in [ADR 001: role storage and API authorization](docs/adr/001-role-storage-and-api-authorization.md) and [ADR 002: frontend permissions and forbidden states](docs/adr/002-frontend-permissions-and-forbidden-states.md).

```mermaid
flowchart TD
    UI[React app] -->|Bearer token| AUTH[FastAPI authentication dependency]
    AUTH --> DB[(Load current user from PostgreSQL)]
    AUTH -->|Missing or invalid credentials| UNAUTH[401: sign in]
    DB -->|Account no longer exists| UNAUTH
    DB -->|Inactive account| DENIED[403: Access Denied]
    DB -->|Active user| POLICY[Endpoint role and ownership checks]
    POLICY --> DENIED
    POLICY --> HANDLER[Run allowed endpoint and return response]
    HANDLER -->|User role from /users/me| UI
    UI --> MAP[Frontend permission map]
    MAP --> NAV[Hide unavailable links and controls]
    MAP --> GUARD[Guard protected routes]
    GUARD -->|Denied| PAGE[Access Denied page]
```

## Migrations and checks

`scripts/prestart.sh` runs `alembic upgrade head` and creates the initial admin. Existing databases are migrated automatically; downgrading the role migration maps admins back to superusers and managers/members back to ordinary users.

Backend tests remove their users and items at teardown, so use a separate test database. With the Compose database running, create it once from the repository root:

```bash
docker compose exec db createdb -U postgres app_test
```

Then, from `backend/`, use the PostgreSQL password configured in `.env`:

```bash
export DATABASE_URL='postgresql://postgres:changethis@localhost:5432/app_test'
uv run alembic upgrade head
uv run bash scripts/test.sh
uv run bash scripts/lint.sh
```

For only the authorization scenarios, run `uv run pytest tests/api/routes/test_roles.py`. These cover allowed/denied access, cross-user boundaries, privilege injection, role changes with existing tokens, and authentication failures.

Invalid null values for email, active status, or password return `422` without changing the user. Disabling an account also blocks its existing tokens; the frontend shows Access Denied and allows logout.

With the backend and frontend running, from `frontend/`:

```bash
bunx playwright install chromium
bunx playwright test tests/roles.spec.ts
bun run build
```

Run `bash scripts/generate-client.sh` from the repository root after API schema changes. See [implementation notes](NOTES.md) for verification details and scope limits.

[![Test Docker Compose](../../actions/workflows/test-docker-compose.yml/badge.svg)](../../actions/workflows/test-docker-compose.yml)
[![Test Backend](../../actions/workflows/test-backend.yml/badge.svg)](../../actions/workflows/test-backend.yml)

## Technology Stack and Features

- ⚡ [**FastAPI**](https://fastapi.tiangolo.com) for the Python backend API.
  - 🧰 [SQLModel](https://sqlmodel.tiangolo.com) for the Python SQL database interactions (ORM).
  - 🔍 [Pydantic](https://docs.pydantic.dev), used by FastAPI, for the data validation and settings management.
  - 💾 [PostgreSQL](https://www.postgresql.org) as the SQL database.
- 🚀 [React](https://react.dev) for the frontend.
  - 🧩 Built into the backend application and served by FastAPI on the same domain as the API.
  - 💃 Using TypeScript, hooks, [Vite](https://vitejs.dev), and other parts of a modern frontend stack.
  - 🎨 [Tailwind CSS](https://tailwindcss.com) and [shadcn/ui](https://ui.shadcn.com) for the frontend components.
  - 🤖 An automatically generated frontend client.
  - 🧪 [Playwright](https://playwright.dev) for end-to-end testing.
  - 🦇 Dark mode support.
- ☁️ [FastAPI Cloud](https://fastapicloud.com) for deployment.
- 🐋 [Docker Compose](https://www.docker.com) for local services and self-hosted deployment.
  - 📞 [Traefik](https://traefik.io) as a reverse proxy with automatic HTTPS.
- 🔒 Secure password hashing by default.
- 🔑 JWT (JSON Web Token) authentication.
- 📫 Email-based password recovery.
- ✉️ [React Email](https://react.email) for email templates.
- 📬 [Mailpit](https://mailpit.axllent.org) for local email testing during development.
- ✅ Tests with [Pytest](https://pytest.org).
- 🏭 CI (continuous integration) and CD (continuous deployment) based on GitHub Actions.

### Dashboard Login

![Dashboard login screenshot](img/login.png)

### Dashboard - Admin

![Admin dashboard screenshot](img/dashboard.png)

### Dashboard - Items

![Items dashboard screenshot](img/dashboard-items.png)

### Dashboard - Dark Mode

![Dark mode dashboard screenshot](img/dashboard-dark.png)

### React Email Templates

![Email templates screenshot](img/react-email.png)

### Mailpit - Local Email Testing

![Mailpit screenshot](img/mailpit.png)

### Interactive API Documentation

![API docs](img/docs.png)

## How to Use It

Click the **Use this template** button at the top of this page to create a new repository.

## Backend Development

Backend docs: [backend/README.md](./backend/README.md).

## Frontend Development

Frontend docs: [frontend/README.md](./frontend/README.md).

## Deployment

FastAPI Cloud deployment: [deployment.md](./deployment.md).

Self-hosted deployment with Docker Compose: [deployment-docker-compose.md](./deployment-docker-compose.md).

## Development

General development docs: [development.md](./development.md).

This includes the local FastAPI and Vite workflow, Docker Compose services, `.env` configuration, and more.

## Release Notes

Check the file [release-notes.md](./release-notes.md).

## License

The Full Stack FastAPI Template is licensed under the terms of the MIT license.
