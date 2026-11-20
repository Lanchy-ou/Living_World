"""Identity-keyed settlement chance independent of the completion shuffle."""

from hashlib import sha256

from ..rules.schema import canonical_json_bytes


def chance_roll(seed: int, tick: int, rule_id: str, subject: str) -> int:
    k = 0
    while True:
        record = canonical_json_bytes(
            {
                "k": k,
                "rule_id": rule_id,
                "seed": seed,
                "stream": "chance",
                "subject": subject,
                "tick": tick,
            }
        )
        word = int.from_bytes(sha256(record).digest()[:4], "big")
        if word < 4294967000:
            return word % 1000
        k += 1
