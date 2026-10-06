# Audit Logging Policy

Marrowgate Labs Ltd - Version 1.1 - Effective 2026-02-02

This policy sets what Marrowgate records about activity on its systems.

## Collection

Security logs from all production systems are collected centrally in Grafana Loki.

## Storage

Security logs are kept for 13 months.

## Alerting

Security alerts page the on-call engineer through PagerDuty.

Alert rules are maintained by the security team and tuned each quarter to cut noise.
