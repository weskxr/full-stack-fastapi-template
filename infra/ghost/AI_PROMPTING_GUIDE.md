# Suggested AI prompts

A recommended workflow for this task, not a transcript of the original conversation.

1. Read the task and inspect the repository first. Don't edit files yet. Clarify what “one click” means and list the required accounts, credentials and domain setup.

2. Compare practical tunnel providers and provisioning options. Recommend the simplest complete solution and explain its trade-offs.

3. Define the network and authentication boundaries. Keep SSH inaccessible publicly from the first boot, including during bootstrap and recovery. Cover both IPv4 and IPv6.

4. Implement one deployment command. Keep this task separate from the existing application and validate configuration before creating resources.

5. Protect Ghost administration and initial owner setup before publishing the site. Keep the public blog and Content API working, with correct HTTPS handling.

6. Review credential handling. Keep provider tokens off the VPS, generate database passwords securely, protect state and logs, and restrict container access to cloud metadata.

7. Pin dependencies and images. Add persistent storage, health checks and automatic service startup. Make retries preserve credentials and existing data.

8. Test interrupted deployments and repeated runs. Reject accidental resource replacement or deletion, and provide useful diagnostics without destroying failed deployments.

9. Add focused tests for access boundaries, encoded admin paths, HTTPS redirects and data persistence. Distinguish mocked checks from real infrastructure tests.

10. Test a fresh VPS: authorized and rejected SSH access, external port scans, reboot recovery and tunnel failure. Report anything you cannot verify.

11. Document prerequisites, deployment, email setup, updates, backups, restore and teardown. Perform a restore drill before claiming the backup process is verified.

12. Review the final diff and run the relevant checks. Report remaining limitations and organize the implementation, tests and documentation into logical commits.
