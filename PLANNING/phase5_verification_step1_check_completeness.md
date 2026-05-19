Created [subsystems/VERIFIED.md](/home/tack/code/villmage/subsystems/VERIFIED.md).

I kept the original structure and only added details where the spec would otherwise change subsystem boundaries or APIs. The main additions were around timed world records and expiry, paused/resumed work, partial crafting, segmented sleep restoration, exact conversation/trade state-machine behavior, scheduled memory compaction, exact prompt-contract enforcement, and perspective-specific replay.

I did not run broader validation beyond the spec-to-definition reconciliation pass, since this step was document-only.