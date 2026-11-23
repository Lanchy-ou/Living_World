"""Inputs shared by DL-04's scheduling, dispatch and settlement vectors."""

import json


def act(action="wait", *, verb=None, params=None, intention=None, mute=(), **fields):
    choice = (
        {"kind": "continue"}
        if action == "continue"
        else {
            "kind": "intent",
            "intent": {
                "action": action,
                "verb": verb,
                "params": params or {},
                "reason": None,
                "inputs": [],
                "target": None,
                "instruments": [],
            },
        }
    )
    return json.dumps(
        dict(
            step="act",
            action=choice,
            utterance=None,
            cite=[],
            intention=intention,
            mute=list(mute),
            **fields,
        )
    )


def report(kind, subject=None, **fields):
    from living_island.world.v2.protocol import WorldReport

    return WorldReport.model_validate(
        {
            "kind": kind,
            "subject_id": subject,
            "band": None,
            "threshold_id": None,
            "addressed": None,
            **fields,
        }
    )
