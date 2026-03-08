# Live Usage Review 2026-03-08

This document records the real issues found during live use against `Tic-tak-toe.exe`, and the changes shipped in `0.2.4` to close them.

## Fixed In 0.2.4

### 1. Native raw-memory tools now accept symbolic addresses consistently

Fixed tools:

- `ce.query_memory`
- `ce.query_memory_map`
- `ce.aob_scan`
- `ce.read_memory`
- `ce.write_memory`
- `ce.resolve_symbol(address=...)`

Before this fix, the Python tool surface documented `int | str`, but the native bridge accepted only raw integers in several paths.

Implementation:

- Added shared `parse_or_resolve_address(...)` handling in the native bridge
- Reused that path across direct address reads and range-based native APIs

## 2. Cheat-table record types now accept common CE UI labels

Fixed behavior:

- `ce.record_set_type(record_id=..., value_type="4 Bytes")`
- `ce.record_create(options={"type": "4 Bytes"})`
- `ce.record_create_many(...)`
- `ce.record_create_group(...)`

Accepted aliases now include common UI strings such as:

- `4 Bytes`
- `8 Bytes`
- `Byte Array`
- `Auto Assembler`

The table runtime also returns cleaner `invalid_record_type:*` messages instead of leaking raw Lua traceback noise.

## 3. Added missing workflow helpers discovered during live use

New tools:

- `ce.normalize_address`
- `ce.verify_target`
- `ce.record_create_many`
- `ce.record_create_group`

These cover the manual workflows that kept recurring during live CE analysis:

- resolve an expression before a raw-memory call
- confirm the current attachment and main module quickly
- build grouped CE record layouts without dropping to ad hoc Lua

## Verification

Validated in the repo after the fix pass:

- Python registry count increased from `192` to `196`
- README, troubleshooting, and release metadata updated to `0.2.4`
- Live suite coverage extended to exercise symbolic native-address paths and the new record helpers

## Follow-Up

This review started as an issue list. It is now a shipped-fix record for the `0.2.4` release.
