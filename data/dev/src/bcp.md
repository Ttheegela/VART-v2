# Business Continuity and Disaster Recovery Plan

Kestrelyn, Inc. - Version 1.0 - Effective 2026-03-10

## Purpose and Scope

This plan describes how Kestrelyn restores Kestrelyn Ledger, and the business functions that support it, after a disaster. It applies to the production service and to the corporate systems that the recovery team needs to do its work. It supports the Business Continuity and Disaster Recovery Policy.

## Recovery Objectives

The recovery time objective (RTO) is 8 hours and the recovery point objective (RPO) is 24 hours.

## Disaster Scenarios

The plan covers these scenarios:

- Loss of the availability zone that hosts the primary production environment
- Loss or corruption of the primary production database
- Loss of the corporate office, or a prolonged power or network outage there
- Loss of a critical third-party service
- Unavailability of key staff

## Recovery Strategy

Recovery uses a replacement environment in a separate availability zone. Data is recovered into the replacement environment before customer traffic is returned to it.

## Assumptions

The plan assumes that the Recovery Coordinator or a deputy can be reached, that the recovery team can work remotely, and that availability zones fail independently of each other.

## Recovery Team and Roles

| Role | Responsibility | Held by |
|---|---|---|
| Recovery Coordinator | Declares the disaster and directs the recovery | CTO |
| Infrastructure Lead | Rebuilds the environment and recovers the data | IT Manager |
| Communications Lead | Keeps employees and customers informed | CEO |

## Recovery Steps

- Declare the disaster and assemble the recovery team
- Confirm the scope of the disruption and which systems are affected
- Create the replacement environment and recover the data
- Check that the service works end to end before returning customer traffic to it
- Tell customers when service is restored
- Hold a debrief and record lessons learned

## Testing

Disaster recovery failover is tested annually; the last failover test was completed in November 2025.

Backup restore tests are performed annually; the last test was completed in November 2025.

## Plan Maintenance

This plan is updated after every test and whenever the production architecture changes significantly.
