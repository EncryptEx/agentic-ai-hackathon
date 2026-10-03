"""Ground-truth labels for seed transactions. EVALUATOR-ONLY: never import this from the agent, tools,
policy, alerts or seed.py. These are the data generator's answer key (fraud / suspicious typology tags),
not evidence of real-world fraud, and they are used only to score finished runs."""

import os
import sqlite3

from .seed import DEFAULT_DB


def _path():
    return os.environ.get("EVIDENCETRAIL_SEED_DB") or DEFAULT_DB


def ground_truth(transaction_id):
    """Return {'is_fraud', 'is_suspicious', 'tag', 'flagged'} for a seed transaction, or None."""
    conn = sqlite3.connect(f"file:{_path()}?mode=ro", uri=True)
    try:
        row = conn.execute("SELECT is_fraud_synthetic, fraud_typology_tag, is_suspicious_synthetic, "
                           "synthetic_typology_tag FROM transactions WHERE transaction_id=?", (transaction_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    fraud, ftag, susp, stag = bool(row[0]), row[1], bool(row[2]), row[3]
    return {"is_fraud": fraud, "is_suspicious": susp, "tag": ftag if fraud else (stag if susp else None),
            "flagged": fraud or susp}
