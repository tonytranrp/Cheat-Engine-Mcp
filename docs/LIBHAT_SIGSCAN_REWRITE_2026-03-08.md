# Libhat Signature Scan Rewrite 2026-03-08

This document records the `0.2.7` signature-scan rewrite and the live validation that followed it.

## Scope

- vendored `libhat` under `native/vendor/libhat`
- rewrote native `ce.aob_scan` around libhat-backed signature parsing and matching
- rewrote `ce.aob_scan_unique` and `ce.aob_scan_module_unique` to use the same native scan path
- added scan controls for:
  - `section_name`
  - `scan_alignment`
  - `scan_hint`
  - `timeout_seconds`
- kept exact `ce.scan_string(...)` on the fast native path for bounded string searches

## User-Facing Changes

- raw signature scans now use libhat instead of the older byte-by-byte matcher
- exact string searches over a module or explicit range now complete on the native scan path instead of dropping into slower CE memscan behavior
- unique signature scans now support the same scoping options as plain `ce.aob_scan`
- PE-section scans fall back to Python-side PE header parsing when the native section resolver cannot produce bounds on a target module

## Live Verification

Target:

- `Minecraft.Windows.exe`

Commands:

```powershell
py -3 .\tools\dev\run-live-tool-suite.py --process-name "Minecraft.Windows.exe" --manage-existing-backend
py -3 .\tools\dev\benchmark-live-tools.py --process-name "Minecraft.Windows.exe" --manage-existing-backend --iterations 12 --scan-iterations 6 --parallel-calls 18 --parallel-workers 6
```

## Results

Full live suite:

- `210/210` tools invoked successfully
- total runtime: `17550.112 ms`
- `ce.aob_scan_unique` on a bounded aligned range: `0.348 ms`
- `ce.aob_scan_module_unique` on the main module: `195.06 ms`
- section-scoped `.text` scan completed successfully through the fallback PE-section resolver path

Focused benchmark:

- `ce.aob_scan(range,x16)`: avg `0.27 ms`
- `ce.aob_scan_unique(range,x16)`: avg `0.28 ms`
- `ce.scan_string(range,ascii)`: avg `0.313 ms`
- `ce.aob_scan_module_unique(main module)`: avg `208.98 ms`
- `parallel_mixed_light` wall time with `18` calls across `6` workers: `8.588 ms`

## Implementation Notes

- native scan alignment is mapped onto libhat alignment controls
- copied remote scan buffers are realigned locally so libhat `x16` scans preserve the attached process address modulo
- the Python tool surface resolves stale one-live-session `session_id` values automatically
- long-running script and scan tools now expose `timeout_seconds` overrides

## Remaining Hotspots

These paths are still slower, but they are not part of the libhat regression set:

- `ce.reinitialize_symbolhandler`
- `ce.debug_start`
- `ce.dissect_module`

Those remain dominated by Cheat Engine and debugger work, not the signature-scan rewrite.
