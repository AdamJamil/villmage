The file hierarchy and object assignments are appended to `impl/observability.md`.

**Summary of decisions:**

- **Two files**: `observability/types.py` for all Python on-disk schema types, `observability/viewer.html` for the standalone viewer.
- **Python side** owns: `DeltaKind`, `FieldChange`, `DeltaRecord`, `VillagerMemoryCheckpoint`, `CheckpointRecord` — everything that touches disk and must be importable by Simulation Engine / Memory System.
- **JS side** owns: `VillagerViewerState`, `WorldViewerState`, `ViewerSession` — these are viewer-internal computed objects, never persisted, no Python equivalent needed.
- The viewer is a single self-contained HTML file (embedded CSS + JS) requiring no server, consistent with the spec's offline-only mandate.