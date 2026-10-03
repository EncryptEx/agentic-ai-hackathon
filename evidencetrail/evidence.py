"""Evidence store: every tool response is stored here before the agent sees it."""

from .canon import now_utc, sha256


class EvidenceStore:
    def __init__(self):
        self._items = {}
        self._order = []

    def add(self, type_, source, source_record_id, payload) -> dict:
        evidence_id = f"EV-{len(self._order) + 1:03d}"
        item = {
            "evidence_id": evidence_id,
            "type": type_,
            "source": source,
            "source_record_id": source_record_id,
            "payload": payload,
            "observed_at": now_utc(),
            "snapshot_hash": sha256(payload),
        }
        self._items[evidence_id] = item
        self._order.append(evidence_id)
        return item

    def get(self, evidence_id):
        return self._items.get(evidence_id)

    def has(self, evidence_id) -> bool:
        return evidence_id in self._items

    def all(self) -> list:
        return [self._items[i] for i in self._order]

    def by_type(self, type_) -> list:
        return [e for e in self.all() if e["type"] == type_]

    def ids(self) -> list:
        return list(self._order)
