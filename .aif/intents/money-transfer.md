# Transfer money between accounts safely

## Why
Customers move money between accounts. The system must never create or destroy money, and balances must never go negative.

## Scope
- domain/transfer.py
- ports/db.py
- adapters/sqlite_db.py

## Acceptance
- The sum of both balances is unchanged by a transfer.
- A transfer larger than the source balance is rejected by the contract.
- Both updated accounts are persisted through the DbWrite capability.
