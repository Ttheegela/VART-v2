# Data Classification Policy

Kestrelyn, Inc. - Version 1.0 - Effective 2026-01-15

This policy outlines the requirements and controls that Kestrelyn has implemented to manage data throughout its lifecycle.

## Policy Statements

Kestrelyn policy requires that:

(a) Data should be classified at the time of creation or acquisition according to the Kestrelyn data classification model, by labeling or tagging the data.

(b) A data repository carries the label of the most sensitive data it holds.

## Data Classification Model

Kestrelyn classifies data into four levels: Public, Internal, Confidential and Restricted.

| Level | Description | Examples |
|---|---|---|
| Public | Information approved for release outside Kestrelyn. | Marketing pages, published documentation |
| Internal | Information for use inside Kestrelyn that would cause minor harm if exposed. | Internal wiki pages, meeting notes |
| Confidential | Information that would cause significant harm to Kestrelyn or its customers if exposed. | Customer data, contracts, source code |
| Restricted | Information whose exposure would cause severe harm. | Signing keys, bank account numbers |

## Customer Data

Kestrelyn Ledger stores all customer data in AWS us-east-1.

Customer data is deleted within 30 days after the end of the contract.

## Machine Learning

Kestrelyn does not use customer data to train machine learning models.
