# Cryptography Policy

Kestrelyn, Inc. - Version 1.0 - Effective 2026-01-15

Kestrelyn takes the confidentiality and integrity of its customer data very seriously. As stewards and partners of Kestrelyn customers, we strive to assure data is protected from unauthorized access and that it is available when needed. The following policies drive many of our procedures and technical controls in support of the Kestrelyn mission of data protection.

Production systems that create, receive, store, or transmit customer data (hereafter "Production Systems") must follow the requirements and guidelines described in this policy.

## Policy Statements

Kestrelyn policy requires that:

(a) Data must be handled and protected according to its classification requirements and following approved cryptographic standards, if applicable.

(b) Whenever possible, data of the same classification is stored in a given data repository, and sensitive and non-sensitive data are not mixed in the same repository. Security controls are applied according to the highest classification of data in a given repository.

(c) All Production Systems must disable services that are not required to achieve the business purpose or function of the system.

(d) Cryptographic algorithms and key lengths must come from the Kestrelyn approved list, and proprietary algorithms must not be used.

(e) Cryptographic keys must not be stored in source code or in plain text configuration files.

## Cryptographic Standards

Customer data at rest is encrypted with AES-256 using AWS KMS.

Data in transit is encrypted using TLS 1.2 or higher.

AWS KMS encryption keys are rotated annually.
