1. Read the task README and inspect the project first. Dont edit files yet. Show me the gaps and your proposed approach.

2. Compare the simplest RBAC options. Include the permission matrix, migration plan and any assumptions before implementation.

3. Split work between backend, frontend and test agents. Agree on the API contract first and give them separate file ownership.

4. Keep backend permissions authoritative. Check signup and profile updates can't be used to promote yourself or edit another user's data.

5. Reuse the existing UI. Hide unavailable controls and show Access Denied for protected URLs. A 403 shouldn't log users out.

6. Check that changing a role or disabling an account affects its existing tokens too.

7. Add focused tests for each role, including denied requests and cross-user item access. Use a separate test database.

8. Try switching accounts without reloading the page. Make sure cached admin data doesn't stay visible to a member.

9. Check migration backfill and downgrade. Also try invalid roles, null profile fields and updates that dont include a role.

10. Run everything from a clean checkout and fresh database. Seed twice, start the app and log in with all three roles.

11. Update the README with setup, demo users, tests and permissions. Check the commands actually work.

12. Add two ADRs, 200–400 words each, plus a simple auth diagram. Explain the choices and trade-offs in plain English.

13. Review the final diff, run the checks and report remaining gaps. Make logical commits as work is ready. Include the original AI conversations.
