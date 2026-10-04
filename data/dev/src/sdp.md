# Secure Software Development and Product Security

Kestrelyn, Inc. - Version 1.0 - Effective 2026-02-01

Engineering conventions for the Kestrelyn code base are documented on the engineering wiki.

## Policy Statements

Kestrelyn policy requires that:

(a) Kestrelyn software engineering and product development is required to follow security best practices. Product should be "Secure by Design" and "Secure by Default".

(b) Quality assurance activities must be performed, including unit testing and integration testing.

(c) Security requirements must be defined, tracked, and implemented.

## Pull Requests and Testing

Every pull request must be reviewed by a second engineer before it is merged.

Static application security testing (SAST) runs in CI on every pull request.

## Dynamic Testing

Dynamic application security testing (DAST) is not yet performed.

## Frameworks and Libraries

Developers rely on the built-in protections of the actively maintained application framework for input validation and output encoding, following the OWASP ASVS checklist.

## Build and Release

Production builds and deployments run exclusively through the CI/CD pipeline from the main branch.
