# Software Delivery Policy

Marrowgate Labs Ltd - Version 1.3 - Effective 2026-03-02

This policy governs how code reaches production.

## Source Control

All code lives in GitHub. The main branch is protected.

No pull request is merged until a second engineer has approved it.

## Automated Checks

Static application security testing (SAST) runs on every pull request in CI.

Dynamic application security testing (DAST) is not part of the release process.

## Frameworks

Developers use the validation and output-encoding features of the maintained web framework instead of writing their own.

## Releases

Only the CI/CD pipeline can deploy to production, and it deploys only from the main branch.
