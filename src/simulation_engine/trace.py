"""Event trace — the project's stable public contract.

Every state transition passes through a block, and every block emits trace
records, so instrumentation is complete by construction. The same trace file
drives the replay animation, KPI recomputation, process maps, and — not least
— gives the agent that wrote the model a text artifact to debug against.

Schema (one JSON object per line in ``trace.jsonl``):

    { run_id, seq, t, entity_id, entity_type, event, block, resource,
      resource_unit, from_block, to_block, t_start, t_end, attrs }

``seq`` is a monotonic tie-break so simultaneous events replay
deterministically. Movement/delay events carry ``t_start``/``t_end`` so the
viewer tweens positions client-side — we emit semantics, not pixels.
"""

from __future__ import annotations

import json
from typing import Any

# Event vocabulary (extends the vidigi convention).
ARRIVAL = "arrival"
DEPART = "depart"
QUEUE_JOIN = "queue_join"
QUEUE_LEAVE = "queue_leave"
BALK = "balk"
RENEGE = "renege"
SEIZE_REQUEST = "seize_request"
SEIZE = "seize"
RELEASE = "release"
DELAY_START = "delay_start"
DELAY_END = "delay_end"
MOVE = "move"
ENTER_BLOCK = "enter_block"
STATE = "state"

TRACE_OFF = "off"
TRACE_FULL = "full"


class Trace:
    """In-memory trace recorder, written to JSONL at the end of a run.

    ``level="off"`` turns recording into a no-op (Monte Carlo batches run with
    the trace off and animate one representative run).
    """

    def __init__(self, run_id: int = 0, level: str = TRACE_FULL):
        self.run_id = run_id
        self.enabled = level != TRACE_OFF
        self._seq = 0
        self.records: list[dict[str, Any]] = []

    def emit(
        self,
        t: float,
        event: str,
        entity=None,
        block: str | None = None,
        **fields: Any,
    ) -> None:
        if not self.enabled:
            return
        rec: dict[str, Any] = {
            "run_id": self.run_id,
            "seq": self._seq,
            "t": round(float(t), 9),
            "event": event,
        }
        self._seq += 1
        if entity is not None:
            rec["entity_id"] = entity.id
            rec["entity_type"] = entity.type
        if block is not None:
            rec["block"] = block
        for k, v in fields.items():
            if v is not None:
                rec[k] = v
        self.records.append(rec)

    def to_jsonl(self, path: str) -> None:
        with open(path, "w") as f:
            for rec in self.records:
                f.write(json.dumps(rec) + "\n")

    def __len__(self) -> int:
        return len(self.records)
