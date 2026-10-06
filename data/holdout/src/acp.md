# Access Control Standard

Marrowgate Labs Ltd - Version 1.4 - Effective 2026-02-16

Scope: this standard applies to internal systems, which are the corporate and engineering systems that Marrowgate staff use to run the company, such as Entra ID, AWS, GitHub, the HR information system and the Marrowgate Payroll admin console.

Access to Marrowgate systems is limited to authorized people, including employees, contractors and consultants. Everyone is responsible for reporting suspected misuse of an account.

## Standard

### Authentication

Marrowgate requires that:

(a) Every system must authenticate each person with an account that is unique to that person.

(b) Shared accounts are not allowed except for documented break-glass access.

(c) Sessions must time out after a period of inactivity.

Every internal system is accessed through Microsoft Entra ID single sign-on (SSO).

Multi-factor authentication (MFA) is required for every internal system.

Every account that signs in with a password, for staff and for customers, must use a password of at least 16 characters.

### Authorization and Leavers

Marrowgate requires that:

(a) Every access request is approved by the requester's manager before it is granted.

(b) Production access needs an extra approval from the security team.

Access is assigned by role and limited to what each role needs.

Access to internal systems is recertified every quarter by the owner of each system.

Access to internal systems is removed on the day a person leaves, and in any case within 24 hours.

### Privileged Access

Marrowgate requires that:

(a) Administrators use a separate privileged account and never their everyday account.

(b) Privileged sessions to production go through the bastion service, which records each session.
