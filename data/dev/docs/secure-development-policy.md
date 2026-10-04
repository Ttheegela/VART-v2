# Secure Software Development and Product Security

Kestrelyn, Inc. - Version 1.0 - Effective 2026-02-01

The Kestrelyn development team follows security best practices when developing software, and automates security testing throughout the development lifecycle whenever possible.

Security is integrated into all phases of the Kestrelyn product development lifecycle, including:

- Secure design: application risk classification, security requirement definition, secure application design and threat modeling
- Secure development and testing: linting with security rules and the security testing described in this policy

Engineering conventions for the Kestrelyn code base are documented on the engineering wiki.

## Policy Statements

Kestrelyn policy requires that:

(a) Kestrelyn software engineering and product development is required to follow security best practices. Product should be "Secure by Design" and "Secure by Default".

(b) Quality assurance activities must be performed, including unit testing and integration testing.

(c) Threat modeling must be performed for a new product or major changes to an existing product.

(d) Security requirements must be defined, tracked, and implemented.

## Pull Requests and Testing

Every pull request must be reviewed by a second engineer before it is merged.

Static application security testing (SAST) runs in CI on every pull request.

## Dynamic Testing

Dynamic application security testing (DAST) is not yet performed.

## Frameworks and Libraries

Developers rely on the built-in protections of the actively maintained application framework for input validation and output encoding, following the OWASP ASVS checklist.

## Build and Release

Production builds and deployments run exclusively through the CI/CD pipeline from the main branch.
