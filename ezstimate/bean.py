"""Optional real BEAN Core CommandInbox transport; never simulate a BEAN answer."""
from __future__ import annotations
import json
from pathlib import Path
import uuid

def send_to_bean_inbox(proposal: dict, inbox_dir: str | Path) -> Path:
    """Write an unverified, clearly identified quotation *note* for actual BEAN Core."""
    if proposal.get("schema") != "ezstimate.quote_proposal.v1" or proposal.get("status") != "review_required":
        raise ValueError("only review-pending EZstimate proposals are allowed")
    dest = Path(inbox_dir)
    if not dest.is_dir():
        raise ValueError("real BEAN inbox directory is required")
    summary = f"EZstimate review_required quote {proposal['quote_number']}: " \
              f"proposed USD {proposal['pricing']['quoted_total']}; not approved, " \
              f"not customer accepted; sources require review."
    payload = {"command": "log_note", "from": "ezstimate", "args": {"text": summary}}
    name = dest / f"ezstimate-{uuid.uuid4().hex}.json"
    name.write_text(json.dumps(payload), encoding="utf-8")
    return name
