"""Fixture-only input units; never a tokenizer or counter for a hosted model.

The fake model assigns one input unit to each consecutive block of at most 1024
retained wire bytes. Ceiling division is its exact input count. This definition
is pinned in the closed tape and fake registration, whose prices are zero.
"""

COUNTER_ID = "fixture-p3-05-wire-chunks"
COUNTER_VERSION = "0.1"


def count_input_units(body: bytes) -> int:
    if type(body) is not bytes:
        raise TypeError("the fixture counter requires exact wire bytes")
    return (len(body) + 1023) // 1024
