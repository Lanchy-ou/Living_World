"""Seed a resident store with an earlier skill hypothesis."""


def add_skill(store, status, recipe):
    record = store.registry.parse(
        {
            "id": store.snapshot.next_id(),
            "owner_id": store.snapshot.owner_id,
            "kind": "skill",
            "content": {"hypothesis": recipe, "evidence": {}, "status": status},
            "sources": [{"kind": "observed", "entry_id": "d:earlier:1"}],
            "created_tick": 0,
            "updated_tick": 0,
            "about_tick": None,
            "confidence": 2,
            "speech_derived": False,
            "last_used_tick": None,
            "use_count": 0,
            "supersedes": None,
            "superseded_by": None,
            "needs_review": False,
            "gist": f"My {recipe['verb']} technique",
            "text": None,
        }
    )
    store.apply(store.snapshot.version, "change_set", (record,))
    return record.id
