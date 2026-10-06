# Cryptography Standard

Marrowgate Labs Ltd - Version 1.1 - Effective 2026-02-02

This standard sets the cryptographic controls used to protect Marrowgate data.

## Data at Rest

Customer data at rest is encrypted with AES-256 using AWS KMS keys.

## Data in Transit

All data in transit is encrypted with TLS 1.2 or TLS 1.3.

Marrowgate Payroll is served only over HTTPS, and plain HTTP requests are refused.

## Key Management

AWS KMS keys are rotated automatically every year.

Key administrators and key users are separate roles, and no single person can both change a key policy and use the key.
