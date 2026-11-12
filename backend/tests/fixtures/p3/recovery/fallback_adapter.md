# Retained P3-04 fallback regression source

`fallback_adapter.py` is the byte-exact production source at P3-04 commit
`10ad22aa399fdf354c5df844b9055759dc582d83`, from
`backend/src/living_island/agents/llm/fallback.py`.
[The provenance pin](fallback_adapter.json) records its commit, path and SHA-256.
Do not hand-edit this snapshot or substitute a fake implementation.

The owner authorized this fixture for acceptance finding P303-A1. It permits the
P3-03 branch to test the real adapter without editing or importing the parallel
P3-04 implementation into its production scope. The fixture uses the actual
frozen rule policy and the shared exception from P3-02 contract commit
`48ff29e5ba363b8d1a0c4a9386e279e2c204ba11`.

[Transaction tests](../../../p3/test_transactions.py) verify the retained bytes
against the pin before loading them. When the production fallback module is
present in an integrated checkout, those same tests import it directly instead.
Neither mode skips the integration cases. Fault injection alters only the rule
proposal returned to the real adapter, or raises an unclassified rule exception;
the adapter's validation, rollback and failure signal execute unchanged.

Coverage includes LLM reentry, continuous fallback, rule primary, wrong plan/actor/
tick/intent identities, missing plan, rollback of all prior private fields,
one wait and one commit, subsequent decisions, propagated ValueError/RuntimeError/
OSError, retained attempt debits and replay with raising external-port sentinels.
