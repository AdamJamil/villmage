"""Parse speeches and memories from transcript markdown files."""

from __future__ import annotations

import re
from pathlib import Path

SPEECH_RE = re.compile(
    r'\*\*(.+?)\*\* `\[(\d+)\]`:\s*(.+?)(?=\n\*\*[A-Z]|\n---|\n<details|\Z)',
    re.DOTALL,
)

MEM_RE = re.compile(
    r'- \*\*(.+?)\*\*: (\[Day.+?\].+?)(?=\n- \*\*|\n\n</details>)',
    re.DOTALL,
)

PHASE_TITLES = {"morning": "Morning", "afternoon": "Afternoon", "evening": "Evening"}


def find_earliest_transcript() -> Path:
    """Return the day_1.md from the earliest timestamped transcript directory."""
    transcripts_dir = Path(__file__).resolve().parent.parent / "transcripts"
    dirs = sorted(d for d in transcripts_dir.iterdir() if d.is_dir())
    if not dirs:
        raise FileNotFoundError(f"No transcript directories in {transcripts_dir}")
    day1 = dirs[0] / "day_1.md"
    if not day1.exists():
        raise FileNotFoundError(f"No day_1.md in {dirs[0]}")
    return day1


def parse_assignments(text: str) -> dict[str, dict[str, list[str]]]:
    """Parse location assignment tables from transcript header.

    Returns {phase: {location_name: [villager_names]}}.
    """
    assignments: dict[str, dict[str, list[str]]] = {}
    for phase, title in PHASE_TITLES.items():
        start = text.find(f"## {title}\n")
        if start == -1:
            continue
        # Read lines until next section or conversation header
        rest = text[start + len(f"## {title}\n"):]
        lines = []
        for line in rest.splitlines():
            if line.startswith("##") or line.startswith("###"):
                break
            lines.append(line)

        phase_locs: dict[str, list[str]] = {}
        for line in lines:
            # Format: **Location Name** — Name1, Name2, Name3
            # or:    **Location Name** — Name1 *(alone)*
            # or:    **Location Name** — *empty*
            m = re.match(r'\*\*(.+?)\*\*\s*[—–-]\s*(.+)', line)
            if not m:
                continue
            loc_name = m.group(1)
            names_part = m.group(2).strip()
            if "*empty*" in names_part:
                continue
            # Strip *(alone)* annotation
            names_part = re.sub(r'\s*\*\(alone\)\*', '', names_part)
            names = [n.strip() for n in names_part.split(",") if n.strip()]
            if names:
                phase_locs[loc_name] = names
        assignments[phase] = phase_locs
    return assignments


def parse_speeches(
    text: str,
    assignments: dict[str, dict[str, list[str]]],
) -> dict[tuple[str, str], list[tuple[str, int, str]]]:
    """Return {(phase, location): [(speaker, score, text), ...]}."""
    convos: dict[tuple[str, str], list[tuple[str, int, str]]] = {}
    for phase, title in PHASE_TITLES.items():
        start = text.find(f"## {title}\n")
        if start == -1:
            continue
        rest = text[start + len(f"## {title}\n"):]
        end_match = re.search(r'\n## (?:Morning|Afternoon|Evening|End of Day)', rest)
        section = text[start:start + len(f"## {title}\n") + (end_match.start() if end_match else len(rest))]

        # Build villager -> location map for this phase
        loc_map: dict[str, str] = {}
        for loc, names in assignments.get(phase, {}).items():
            for n in names:
                loc_map[n] = loc

        speeches = SPEECH_RE.findall(section)
        for name, score, speech_text in speeches:
            loc = loc_map.get(name, "UNKNOWN")
            key = (phase, loc)
            if key not in convos:
                convos[key] = []
            convos[key].append((name, int(score), speech_text.strip()))
    return convos


def parse_memories(text: str) -> list[tuple[str, str]]:
    """Return [(villager_name, memory_text), ...] in transcript order."""
    return MEM_RE.findall(text)


def load_history_lines(transcript_path: Path | None = None) -> list[str]:
    """Extract dialogue lines from the first multi-person conversation.

    Returns lines in the format used by the simulation's history:
    "Speaker Name: speech text"
    """
    if transcript_path is None:
        transcript_path = find_earliest_transcript()
    text = transcript_path.read_text()
    assignments = parse_assignments(text)
    speeches = parse_speeches(text, assignments)

    # Find the first conversation (morning phase, first location with 2+ villagers)
    for phase in ["morning", "afternoon", "evening"]:
        for loc, names in assignments.get(phase, {}).items():
            if len(names) >= 2:
                key = (phase, loc)
                if key in speeches:
                    return [f"{name}: {stext}" for name, _, stext in speeches[key]]
    return []


def load_memories(transcript_path: Path | None = None) -> list[str]:
    """Extract all memory texts from a transcript file."""
    if transcript_path is None:
        transcript_path = find_earliest_transcript()
    text = transcript_path.read_text()
    return [mem_text for _, mem_text in parse_memories(text)]
