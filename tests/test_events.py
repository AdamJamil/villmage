# pyre-strict

"""Tests for simulation event dataclasses and heap ordering."""

from heapq import heappop, heappush

from villmage.events import (
    ActionCompleteEvent,
    CarcassRotEvent,
    CheckpointEvent,
    FireExtinctionEvent,
    MidnightEvent,
    ScheduledEvent,
)


def _event_key(event: ScheduledEvent) -> tuple[int, int]:
    """Return the heap-ordering key shared by all scheduled events."""

    return (event.timestamp, event.sequence)


def test_scheduled_events_order_on_timestamp_then_sequence_only() -> None:
    """Mixed scheduled events compare only on timestamp and sequence."""

    events: list[ScheduledEvent] = []
    heappush(events, MidnightEvent(720, 4))
    heappush(events, ActionCompleteEvent(360, 2, "sewalt"))
    heappush(events, CheckpointEvent(360, 3))
    heappush(events, FireExtinctionEvent(360, 1))
    heappush(events, CarcassRotEvent(360, 5, 99))
    heappush(events, ActionCompleteEvent(360, 0, "zed"))
    heappush(events, ActionCompleteEvent(360, 6, "aldric"))

    extracted = [heappop(events) for _ in range(len(events))]
    extracted_keys = [_event_key(event) for event in extracted]

    assert extracted_keys == sorted(extracted_keys)
    assert extracted[0] == ActionCompleteEvent(360, 0, "nobody")
    assert extracted[2] == ActionCompleteEvent(360, 2, "aldric")


def test_action_complete_event_ignores_villager_id_in_comparisons() -> None:
    """ActionCompleteEvent equality and ordering ignore villager payload."""

    assert ActionCompleteEvent(360, 0, "aldric") == ActionCompleteEvent(360, 0, "sewalt")
    assert ActionCompleteEvent(360, 0, "aldric") < ActionCompleteEvent(360, 1, "aldric")


def test_carcass_rot_event_ignores_carcass_id_in_comparisons() -> None:
    """CarcassRotEvent equality and ordering ignore carcass payload."""

    assert CarcassRotEvent(360, 0, 1) == CarcassRotEvent(360, 0, 99)
    assert CarcassRotEvent(360, 0, 1) < CarcassRotEvent(360, 1, 1)


def test_mixed_type_heap_extraction_matches_canonical_startup_order() -> None:
    """Canonical startup heap pops in strict timestamp-sequence order."""

    events: list[ScheduledEvent] = []
    heappush(events, MidnightEvent(1440, 6))
    heappush(events, ActionCompleteEvent(360, 0, "aldric"))
    heappush(events, CheckpointEvent(540, 7))
    heappush(events, CarcassRotEvent(500, 3, 1))
    heappush(events, FireExtinctionEvent(400, 2))

    extracted = [_event_key(heappop(events)) for _ in range(len(events))]

    assert extracted == [
        (360, 0),
        (400, 2),
        (500, 3),
        (540, 7),
        (1440, 6),
    ]
