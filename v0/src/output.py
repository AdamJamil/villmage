"""Terminal formatting and transcript file writer."""

import os
from datetime import datetime
from typing import Dict, List, Optional, TextIO, Tuple, TYPE_CHECKING

from data import Villager

if TYPE_CHECKING:
    from data import Location

# ANSI color codes — one per villager
_VILLAGER_COLORS = {
    "Margot Thistle": "\033[38;5;213m",   # pink
    "Denn Corvale": "\033[38;5;244m",      # gray
    "Sable Dunmore": "\033[38;5;214m",     # orange
    "Pell Arenway": "\033[38;5;114m",      # green
    "Orla Fenn": "\033[38;5;137m",         # brown
    "Aldric Moss": "\033[38;5;111m",       # blue
    "Wren Calloway": "\033[38;5;183m",     # lavender
    "Ham Birch": "\033[38;5;179m",         # wheat
}
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"


def _color_name(name: str) -> str:
    color = _VILLAGER_COLORS.get(name, "")
    return f"{color}{name}{_RESET}" if color else name


class Output:
    day: Optional[int] = None
    file: Optional[TextIO] = None
    phase: Optional[str] = None

    def __init__(self, transcript_dir: str = "transcripts") -> None:
        """
        Get current timestamp and use it to set directory name.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self._dir = os.path.join(transcript_dir, timestamp)

        os.makedirs(self._dir, exist_ok=True)
        print(f"Transcripts: {self._dir}/\n")

    def _create_file(self) -> None:
        """
        Create file for current day and updates the existing file handle.
        """
        if self._file:
            self._file.close()
        path = os.path.join(self._dir, f"day_{self.day}.md")
        self._file = open(path, "w")
        

    def _write_md(self, text: str) -> None:
        if self._file:
            self._file.write(text + "\n")
            self._file.flush()
        else:
            raise Exception("Cannot write output to file - no file currently open.")

    def close(self) -> None:
        if self._file:
            self._file.close()
            self._file = None

    # --- Day / phase structure ---

    def day_start(self, day: int) -> None:
        self.day = day

        self._create_file(day)
        self._write_md(f"# Day {day}\n")
        print(f"\n{_BOLD}{'='*60}")
        print(f"  DAY {day}")
        print(f"{'='*60}{_RESET}\n")

    def phase_start(self, phase: str, location_assignments: Dict["Location", str]) -> None:
        """Print and write the phase header with location assignments."""
        self.phase = phase

        self._write_md(f"\n---\n\n## {phase.capitalize()}\n")
        print(f"{_BOLD}--- {phase.capitalize()} ---{_RESET}\n")

        for loc, villagers in location_assignments.items():
            if not villagers:
                loc_line = f"**{loc.name}** — *empty*"
                print(f"  {_DIM}{loc.name} — empty{_RESET}")
            elif len(villagers) == 1:
                loc_line = f"**{loc.name}** — {villagers[0].name} *(alone)*"
                print(f"  {_BOLD}{loc.name}{_RESET} — {_color_name(villagers[0].name)} (alone)")
            else:
                names = ", ".join(v.name for v in villagers)
                loc_line = f"**{loc.name}** — {names}"
                colored = ", ".join(_color_name(v.name) for v in villagers)
                print(f"  {_BOLD}{loc.name}{_RESET} — {colored}")
            self._write_md(loc_line)
        print()

    # --- Conversation ---

    def conversation_header(self, location_name: str, villager_names: List[str], turn_count: int | None = None) -> None:
        names = ", ".join(villager_names)
        self._write_md(f"\n---\n\n### {location_name} — {self.phase.capitalize()}")
        if turn_count is not None:
            self._write_md(f"*{names} — {turn_count} turns*\n")
        else:
            self._write_md(f"*{names}*\n")
        print(f"  {_BOLD}{location_name}{_RESET}")

    def speech(self, speaker: str, score: int, text: str) -> None:
        self._write_md(f"**{speaker}** `[{score}]`: {text}\n")
        print(f"    {_color_name(speaker)} {_DIM}[{score}]{_RESET}: {text}")

    def departure(self, name: str):
        self._write_md(f"*{name} left.*\n")
        print(f"    {_DIM}{name} left.{_RESET}")

    def ratings_display(self, ratings: dict) -> None:
        """Show ratings inline — dim, for context."""
        parts = []
        for name, score in ratings.items():
            parts.append(f"{name}: {score}")
        line = " | ".join(parts)
        print(f"    {_DIM}ratings: {line}{_RESET}")

    def conversation_end(self) -> None:
        print()

    # --- Memories ---

    def memories_saved(self, memories: Dict[str, str]) -> None:
        """Write memory summary block."""
        self._write_md("<details><summary>Memories saved</summary>\n")
        for name, mem in memories.items():
            self._write_md(f"- **{name}**: {mem}")
        self._write_md("\n</details>\n")

    # --- End of day ---

    def day_end(self, villagers: List[Villager], location_tracker: Dict[Tuple[str, str], str]) -> None:
        """Write end-of-day summary tables."""
        self._write_md(f"\n---\n\n## End of Day {self.day}\n")

        # Where everyone went
        self._write_md("### Where everyone went")
        phases = ["morning", "afternoon", "evening"]
        header = "| | " + " | ".join(p.capitalize() for p in phases) + " |"
        sep = "|---|" + "|".join(["---"] * len(phases)) + "|"
        self._write_md(header)
        self._write_md(sep)
        for v in villagers:
            locs = " | ".join(
                location_tracker.get((v.name, p), "—") for p in phases
            )
            self._write_md(f"| {v.name} | {locs} |")

        # Social interactions
        self._write_md("\n### Social interactions")
        names = [v.name for v in villagers]
        header = "| | " + " | ".join(names) + " |"
        sep = "|---|" + "|".join(["---"] * len(names)) + "|"
        self._write_md(header)
        self._write_md(sep)

        # Count shared locations
        interaction_counts: Dict[Tuple[str, str], int] = {}
        for (vname, phase), loc in location_tracker.items():
            for (vname2, phase2), loc2 in location_tracker.items():
                if phase == phase2 and loc == loc2 and vname < vname2:
                    key = (vname, vname2)
                    interaction_counts[key] = interaction_counts.get(key, 0) + 1

        for v in villagers:
            cells = []
            for v2 in villagers:
                if v.name == v2.name:
                    cells.append("-")
                else:
                    a, b = (v.name, v2.name) if v.name < v2.name else (v2.name, v.name)
                    count = interaction_counts.get((a, b), 0)
                    cells.append(str(count) if count else "")
            self._write_md(f"| {v.name} | " + " | ".join(cells) + " |")

        # All memories
        self._write_md("\n### All memories at end of day")
        for v in villagers:
            self._write_md(f"<details><summary>{v.name} ({len(v.memories)} memories)</summary>\n")
            for i, m in enumerate(v.memories, 1):
                self._write_md(f"{i}. {m}")
            self._write_md("\n</details>\n")

        print(f"\n{_BOLD}End of Day {self.day}{_RESET}\n")
