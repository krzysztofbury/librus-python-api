# Security

Please do not report vulnerabilities or expose school data in public issues.
Report vulnerabilities privately through the repository's **Security** tab
(**Report a vulnerability**) or by email to
[contact@datacraze.io](mailto:contact@datacraze.io).

Include the affected version or commit, steps to reproduce, expected and
observed behavior, and impact. Redact credentials, context keys, cookies, tokens, and any
identifiable school data from reports and attachments.

The [client API security review](contracts/api-security-review.md) maps the
outbound-client threat boundary and existing controls to Snyk's OWASP API guidance.
It also records consumer authorization/serialization responsibilities and local
filesystem/persistence limits; it is not a third-party security certification.

## Repository protections

The default branch requires a pull request and the CI checks, and refuses force
pushes and deletion. Secret scanning with push protection, Dependabot alerts and
security updates, CodeQL default setup and private vulnerability reporting are
enabled. Workflows default to a read-only token and need approval before running
for outside contributors.
