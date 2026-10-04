# SOC 2 Type II Report Summary

Kestrelyn, Inc. - Examination period: 2025-07-01 to 2026-06-30

Scope: this report covers the production environment.

This summary describes the independent service auditor's examination of the Kestrelyn Ledger production environment and the main results of that examination. It does not replace the full report.

## Independent Service Auditor's Opinion

The service auditor issued an unqualified opinion on the Company's SOC 2 Type II examination for the period 2025-07-01 to 2026-06-30.

The examination covered the Security category of the AICPA trust services criteria. A Type II examination tests whether controls were suitably designed and whether they operated effectively throughout the whole period, not only on a single date.

Management is responsible for preparing the description of the system and for the design, implementation and operation of the controls. The service auditor is responsible for expressing an opinion based on the examination.

## System Description

Kestrelyn, Inc. (the Company) provides Kestrelyn Ledger, a cloud-based application that helps finance teams capture, approve and pay supplier invoices. The description follows the five components of a service organization's system: infrastructure, software, people, procedures and data.

### Infrastructure

All of the Company's data processing infrastructure is hosted in Amazon Web Services.

### Software

Kestrelyn Ledger is a multi-tenant web application with a public API. Internal services support invoice capture, approval workflows and payment file generation.

### People

The Company has 85 employees, organized into engineering, product, customer success, security and IT, and finance and people teams.

### Procedures

Management has written procedures for operating and supporting the system.

### Data

The system processes supplier invoice data on behalf of customers, together with the user accounts needed to sign in.

## System Operations

Security logs are retained for 90 days.

## Tests of Controls

The auditor tested the design of controls and the operating effectiveness of controls throughout the examination period, using inquiry, observation, inspection of records and re-performance. Samples of 25 items were used for tests that draw from a population of events, such as terminated users.

The controls tested are organized under the nine common criteria series, CC1 through CC9, of the Security category.

## Exceptions Noted

The auditor noted one exception during testing.

For 2 of 25 terminated users sampled, access was removed 5 days after termination.

Management's response to the exception is included in the full report.

## Other Information Provided by the Company

The following information was provided by the Company. It is not covered by the auditor's opinion.

The Company does not currently operate a public bug bounty program.
