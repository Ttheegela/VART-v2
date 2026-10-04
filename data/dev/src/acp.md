# Access Control Policy

Kestrelyn, Inc. - Version 1.0 - Effective 2026-02-01

Scope: this policy applies to internal systems, which are the corporate and engineering systems that Kestrelyn staff use to run the company, such as Okta, AWS, GitHub, Google Workspace and the Kestrelyn Ledger admin console.

Access to Kestrelyn systems and applications is limited to authorized users, including workforce members, contracted providers, consultants and any other entity. All users are responsible for reporting unauthorized use of, or access to, the organization's information systems.

## Policy Statements

### Authentication

Kestrelyn policy requires that:

(a) Access to all computing resources, including servers, end-user computing devices, network equipment, services and applications, must be protected by authentication and authorization.

(b) Interactive user access must be associated to an account or login unique to each user.

(c) A unique access key or service account must be used for each application or user access.

(d) Authenticated sessions must time out after a defined period of inactivity.

All internal systems are accessed through Okta single sign-on (SSO).

Multi-factor authentication (MFA) is required for all internal systems.

Okta enforces a minimum password length of 14 characters.

### Access Authorization and Termination

Kestrelyn policy requires that:

(a) All access requests to computing resources must be approved by the requestor's manager before access is granted.

(b) Access to critical resources, such as production environments, must be approved by the security team in addition to the requestor's manager.

Access to internal systems is role-based and follows the principle of least privilege.

User access to internal systems is reviewed quarterly.

User access to internal systems is removed within 24 hours of termination.

### Shared Secrets Management

Kestrelyn policy requires that:

(a) Use of shared credentials and secrets must be minimized and approved on an exception basis.

(b) If required by business operations, shared secrets must be stored in the approved secrets vault.

(c) Use of a shared secret to access a critical system or resource must be supported by a complementary solution that uniquely identifies the user.

### Privileged Access Management

Kestrelyn policy requires that:

(a) Users must not log in directly to systems as a privileged user. A privileged user is someone with administrative access to critical systems, such as the root user of a Linux system or of an AWS account.

(b) Privileged access must only be gained through a proxy, or equivalent, that supports strong authentication using a unique individual account.
