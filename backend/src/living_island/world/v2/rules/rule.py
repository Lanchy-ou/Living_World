"""Normalize and check the closed rule grammar."""

from copy import deepcopy

from .catalog import MUTABLE, Catalog, Variant, state_component, terrain
from .schema import (
    OPS,
    Table,
    array,
    boolean,
    fields,
    identifier,
    integer,
    interval,
    require,
    string,
    table,
    term,
)

PLACES = {
    "actor",
    "actor.tile",
    "target.tile",
    "target.contents",
    "target.store",
    "subject.tile",
    "subject.contents",
    "subject.store",
    "subject.place",
}

CONDITIONS = {
    "awareness": "value",
    "need": "need op value",
    "free_slots": "op value",
    "terrain_near": "terrain distance",
    "entity_near": "where distance",
    "terrain_at": "of terrain",
    "state": "of field op value",
    "time_phase": "value",
    "work_complete": "",
}
EFFECTS = {
    "need": ("need delta timing", ""),
    "consume": ("of", "quantity archetype"),
    "move": ("from to quantity", "archetype"),
    "set_state": ("of field", "set add"),
}


def phenomena(value: object, catalog: Catalog, path: str) -> None:
    for item in array(value, path):
        term(item, catalog.vocabulary.phenomena, path)


def comparison_tables(catalog: Catalog, enabled: list[str], tables: Table) -> None:
    for verb in sorted(set(enabled) | tables.keys()):
        term(verb, catalog.vocabulary.verbs, verb)
        require(verb in tables, "UNKNOWN_TERM", verb, "missing unmatched comparison table")
        row = fields(tables[verb], verb, "entries default")
        phenomena(row["default"], catalog, verb)
        for entry in array(row["entries"], verb):
            fields(entry, verb, "when phenomena")
            phenomena(entry["phenomena"], catalog, verb)
            comparison = array(fields(entry["when"], verb, "compare")["compare"], verb)
            require(len(comparison) == 3, "BAD_SHAPE", verb, "expected left, operator, right")
            term(comparison[1], OPS, verb)
            for operand in (comparison[0], comparison[2]):
                if type(operand) in (bool, int):
                    continue
                role, _, prop = string(operand, verb).partition(".")
                term(role, ("target", "instrument", "input"), verb)
                term(prop, catalog.vocabulary.properties, verb)
                require(
                    catalog.vocabulary.properties[prop]["domain"] != "count",
                    "BAD_SHAPE",
                    verb,
                    "comparison requires a bool or scale property",
                )


def shape_quantity(value: object, path: str) -> None:
    if isinstance(value, dict):
        fields(value, path, "of", "upto")
        string(value["of"], path)
        if "upto" in value:
            integer(value["upto"], path, 1)
    else:
        integer(value, path, 1)


def shape_place(value: object, roles: set[str], path: str) -> str:
    place = term(value, PLACES, path, "BAD_SHAPE")
    require(place.partition(".")[0] in roles, "BAD_SHAPE", path, "place has no corresponding role")
    return place


def shape_reference(value: object, roles: set[str], path: str) -> None:
    shape_quantity(value, path)
    if not isinstance(value, dict):
        return
    ref: str = value["of"]
    if ref.startswith("fit:"):
        destination = shape_place(ref.removeprefix("fit:"), roles, path)
        require(
            destination.endswith((".store", ".contents")),
            "BAD_SHAPE",
            path,
            "fit requires a store or contents",
        )
        return
    role, _, field = ref.partition(".")
    term(role, roles - {"actor"}, path)
    require(
        field == "quantity" or (field == "store.count" and role in ("subject", "target")),
        "BAD_SHAPE",
        path,
        "invalid quantity reference",
    )


def shape_output(
    output: object, catalog: Catalog, slots: set[str], roles: set[str], path: str
) -> None:
    row = fields(
        output, path, "quantity at", "archetype archetype_from material material_from source"
    )
    require(
        ("archetype" in row) != ("archetype_from" in row),
        "BAD_SHAPE",
        path,
        "output requires exactly one archetype operand",
    )
    require(
        not ("material" in row and "material_from" in row),
        "BAD_SHAPE",
        path,
        "output has competing material operands",
    )
    for key, choices in (
        ("archetype", catalog.archetypes),
        ("material", catalog.materials),
        ("archetype_from", slots),
        ("material_from", slots),
    ):
        if key in row:
            term(row[key], choices, path, "BAD_SHAPE" if key.endswith("_from") else "UNKNOWN_TERM")
    shape_reference(row["quantity"], roles, path)
    shape_place(row["at"], roles, path)
    if "source" in row:
        string(row["source"], path)


def shape_conditions(
    rule: Table, catalog: Catalog, pack: Table, roles: set[str], path: str
) -> dict[str, Table]:
    conditions = {}
    for raw in array(rule.setdefault("conditions", []), path):
        row = table(raw, path)
        name = identifier(row.get("id"), path)
        require(name not in conditions, "DUPLICATE_ID", path, name)
        require(
            name != "world_limit" and name not in {key.removeprefix("slot:") for key in roles},
            "BAD_SHAPE",
            path,
            f"reserved or shared check name {name}",
        )
        kind = term(row.get("kind"), CONDITIONS, path)
        fields(row, path, "id kind " + CONDITIONS[kind])
        conditions[name] = row
        if kind in ("awareness", "need", "free_slots"):
            require("actor" in roles, "BAD_SHAPE", path, "actor-only condition")
        if "op" in row:
            term(row["op"], OPS, path)
        if kind == "awareness":
            term(row["value"], ("awake", "asleep"), path)
        elif kind == "need":
            need = term(row["need"], pack["enabled_needs"], path)
            setting = pack["needs"][need]
            if isinstance(row["value"], str):
                term(row["value"], ("min", "max"), path)
            else:
                integer(row["value"], path, setting["min"], setting["max"])
        elif kind == "free_slots":
            integer(row["value"], path, 0)
        elif kind == "time_phase":
            term(row["value"], ("day", "night"), path)
        elif kind == "state":
            term(row["of"], roles - {"actor"}, path)
            state_component(row["field"], catalog.archetypes, path)
            integer(row["value"], path)
        elif kind == "terrain_at":
            term(row["of"], roles & {"actor", "target", "subject"}, path)
        if "terrain" in row:
            terrain(row["terrain"], path)
        if "where" in row:
            catalog.predicate(row["where"], path)
        if "distance" in row:
            interval(row["distance"], path, 2)
    return conditions


def shape_effect(
    effect: object,
    catalog: Catalog,
    roles: set[str],
    needs: list[str],
    *,
    failure: bool,
    instruments: set[str],
    path: str,
) -> None:
    row = table(effect, path)
    op = term(row.get("op"), EFFECTS, path)
    required, optional = EFFECTS[op]
    fields(row, path, "op " + required, optional)
    if failure:
        require(
            op == "set_state" and isinstance(row["of"], str) and row["of"] in instruments,
            "BAD_SHAPE",
            path,
            "chance-failure effects only mutate instruments",
        )
    if op == "set_state":
        term(row["of"], roles - {"actor"}, path)
        state_component(row["field"], catalog.archetypes, path)
        term(row["field"], MUTABLE, path, "BAD_SHAPE")
        require(("set" in row) != ("add" in row), "BAD_SHAPE", path, "expected set or add")
        integer(row.get("set", row.get("add")), path)
    elif op == "need":
        require("actor" in roles, "BAD_SHAPE", path, "world rule has actor effect")
        term(row["need"], needs, path)
        integer(row["delta"], path)
        term(row["timing"], ("per_tick", "completion"), path)
    else:
        source = string(row["of"] if op == "consume" else row["from"], path)
        role, _, field = source.partition(".")
        term(role, roles - {"actor"}, path)
        if field == "contents":
            require(
                "archetype" in row and "quantity" in row,
                "BAD_SHAPE",
                path,
                "contents debits require archetype and quantity",
            )
        elif op == "move":
            require(
                field == "store" and role in ("target", "subject"),
                "BAD_SHAPE",
                path,
                "move requires contents or a target/subject store",
            )
        else:
            require(
                not field and role in ("target", "subject") and "archetype" not in row,
                "BAD_SHAPE",
                path,
                "invalid entity consume",
            )
        if op == "move":
            shape_place(row["to"], roles, path)
        if "quantity" in row:
            shape_quantity(row["quantity"], path)
            if isinstance(row["quantity"], dict):
                ref = row["quantity"]["of"]
                expected = source + (".count" if field == "store" else ".quantity")
                require(
                    field != "contents" and ref == expected,
                    "BAD_SHAPE",
                    path,
                    "debit quantity must read its own captured count",
                )
        if "archetype" in row:
            term(row["archetype"], catalog.archetypes, path)


def normalize_rule(raw: Table, catalog: Catalog, pack: Table, *, pack_id: str | None) -> Table:
    rule = deepcopy(raw)
    path = identifier(rule.get("id"), "rule")
    trigger = string(rule.get("trigger"), path)
    kind, _, operand = trigger.partition(":")
    term(kind, ("verb", "when", "every"), path)
    is_verb = kind == "verb"
    verb = None
    common = (
        " inputs conditions outputs effects conservation phenomena provenance success_per_mille"
    )
    if is_verb:
        fields(
            rule,
            path,
            "id trigger work_ticks",
            common + " target instruments on_interrupt exhaustion_stops on_chance_failed"
            " chance_failed_effects",
        )
        verb = catalog.vocabulary.verbs[term(operand, pack["enabled_verbs"], path)]
        rule.setdefault("on_interrupt", "lose")
        rule.setdefault("exhaustion_stops", False)
        boolean(rule["exhaustion_stops"], path)
        rule.setdefault("on_chance_failed", "keep_inputs")
        term(rule["on_chance_failed"], ("keep_inputs", "consume_inputs"), path)
        rule.setdefault("chance_failed_effects", [])
    else:
        require("on_interrupt" not in rule, "INTERRUPT_MODE", path, "world rule interrupt")
        fields(rule, path, "id trigger subject", common)
        catalog.predicate(rule["subject"], path)
    chance = integer(rule.setdefault("success_per_mille", 1000), path, 0, 1000)
    require(is_verb or chance == 1000, "BAD_SHAPE", path, "world rule chance must be 1000")
    if kind == "every":
        require(operand.isascii() and operand.isdecimal(), "BAD_SHAPE", path, "invalid period")
        period = integer(int(operand), path, 1)
        rule["trigger"] = f"every:{period}"
    roles = {"actor"} if is_verb else {"subject"}
    names = set()
    if verb is not None:
        kinds = verb["target"]["kinds"]
        require(("target" in rule) == bool(kinds), "BAD_SHAPE", path, "target disagrees with verb")
        if "target" in rule:
            target = fields(rule["target"], path, optional="where terrain")
            require(len(target) == 1, "BAD_SHAPE", path, "expected one target predicate")
            if "terrain" in target:
                require("tile" in kinds, "BAD_SHAPE", path, "unexpected tile target")
                terrain(target["terrain"], path)
            else:
                require(
                    "entity" in kinds or ("resident" in kinds and not target["where"]),
                    "BAD_SHAPE",
                    path,
                    "unexpected entity predicate",
                )
                catalog.predicate(target["where"], path)
            names.add("target")
            roles.add("target")

    for key, maximum in (("instruments", 2), ("inputs", 4)):
        slots = array(rule.setdefault(key, []), path)
        require(len(slots) <= maximum, "BAD_SHAPE", path, f"too many {key}")
        for slot in slots:
            fields(slot, path, "slot where qty")
            name = identifier(slot["slot"], path)
            require(name != "world_limit", "BAD_SHAPE", path, "reserved check name")
            require(name not in names, "DUPLICATE_ID", path, name)
            names.add(name)
            roles.add(f"slot:{name}")
            qty = integer(slot["qty"], path, 1)
            require(
                key != "instruments" or qty == 1,
                "BAD_SHAPE",
                path,
                "instrument quantity must be one",
            )
            catalog.predicate(slot["where"], path)

    conditions = shape_conditions(rule, catalog, pack, roles, path)
    process = False
    if kind == "when":
        condition = conditions[term(operand, conditions, path)]
        process = condition["kind"] == "work_complete"
    require(
        process or not any(c["kind"] == "work_complete" for c in conditions.values()),
        "BAD_SHAPE",
        path,
        "work_complete requires a process trigger",
    )
    if process:
        arch = rule["subject"].get("archetype")
        require(
            arch is not None and "process" in catalog.archetypes[arch]["components"],
            "BAD_SHAPE",
            path,
            "process needs an exact process archetype",
        )

    lists = fields(
        rule.setdefault("phenomena", {}),
        path,
        optional="success unmet chance_failed unmet_by_check",
    )
    for key in ("success", "unmet", "chance_failed"):
        phenomena(lists.setdefault(key, []), catalog, path)
    for check, listing in sorted(table(lists.setdefault("unmet_by_check", {}), path).items()):
        term(check, names | conditions.keys(), path)
        phenomena(listing, catalog, path)

    entity_slots = names if "where" in rule.get("target", {}) else names - {"target"}
    outputs = array(rule.setdefault("outputs", []), path)
    for output in outputs:
        shape_output(output, catalog, entity_slots, roles, path)
    mode = term(
        rule.setdefault("conservation", "inputs_to_outputs"),
        ("source", "none", "inputs_to_outputs"),
        path,
        "BAD_SHAPE",
    )
    require(not outputs or mode != "none", "BAD_SHAPE", path, "none forbids outputs")
    require(
        all(("source" in output) == (mode == "source") for output in outputs),
        "BAD_SHAPE",
        path,
        "conservation disagrees with outputs",
    )

    effects = array(rule.setdefault("effects", []), path)
    instruments = {f"slot:{item['slot']}" for item in rule["instruments"]}
    for effect in effects:
        shape_effect(
            effect,
            catalog,
            roles,
            pack["enabled_needs"],
            failure=False,
            instruments=instruments,
            path=path,
        )
    if process:
        whole = [
            e
            for e in effects
            if e["op"] == "consume" and e["of"] == "subject" and "quantity" not in e
        ]
        require(len(whole) == 1, "BAD_SHAPE", path, "process must consume its whole subject once")

    if verb is not None:
        for effect in array(rule["chance_failed_effects"], path):
            shape_effect(
                effect,
                catalog,
                roles,
                pack["enabled_needs"],
                failure=True,
                instruments=instruments,
                path=path,
            )
        interruption = rule["on_interrupt"]
        if interruption != "lose":
            shape = fields(interruption, path, optional="partial keep_progress")
            require(len(shape) == 1, "INTERRUPT_MODE", path, "invalid interrupt mode")
            if "partial" in shape:
                for output in array(shape["partial"], path):
                    shape_output(output, catalog, entity_slots, roles, path)
            else:
                term(shape["keep_progress"], catalog.archetypes, path, "INTERRUPT_MODE")
        validate_needs(rule, verb, pack, path)

    provenance = rule.get("provenance")
    if pack_id is not None:
        authored = {"kind": "authored", "pack_id": pack_id}
        require(
            provenance is None or provenance == authored,
            "BAD_SHAPE",
            path,
            "file provenance must identify its authoring pack",
        )
        rule["provenance"] = authored
    else:
        row = fields(provenance, path, "kind llm_call_id approved_by approved_at_tick")
        term(row["kind"], ("proposed",), path)
        string(row["llm_call_id"], path)
        string(row["approved_by"], path)
        integer(row["approved_at_tick"], path, 0)
    return rule


def validate_needs(rule: Table, verb: Table, pack: Table, path: str) -> None:
    work = rule["work_ticks"]
    if isinstance(work, dict):
        fields(work, path, "param")
        require(
            isinstance(work["param"], str) and verb.get("duration_param") == work["param"],
            "BAD_SHAPE",
            path,
            "work parameter disagrees with verb",
        )
        work = next(param["min"] for param in verb["params"] if param["name"] == work["param"])
    ticks = integer(work, path, 1)
    rates: dict[tuple[str, bool], int] = {}
    for effect in rule["effects"]:
        if effect["op"] != "need":
            continue
        need, delta = effect["need"], effect["delta"]
        per_tick = effect["timing"] == "per_tick"
        if per_tick:
            require(
                rule["success_per_mille"] == 1000,
                "BAD_SHAPE",
                path,
                "rolling rule cannot have a per-tick delta",
            )
            require(
                not any(c["kind"] == "need" and c["need"] == need for c in rule["conditions"]),
                "BAD_SHAPE",
                path,
                "need check reads a need changed per tick",
            )
        key = (need, delta > 0)
        rates[key] = rates.get(key, 0) + abs(delta) * (ticks if per_tick else 1)
    for (need, gain), rate in sorted(rates.items()):
        limit = pack["needs"][need]["max_gain_per_tick" if gain else "max_loss_per_tick"]
        require(rate <= ticks * limit, "NEED_RATE", path, f"{need} exceeds its rate")


def specificity(rule: Table) -> int:
    target = rule.get("target", {})
    return (
        len(target.get("where", target))
        + len(rule.get("subject", {}))
        + len(rule["conditions"])
        + sum(len(slot["where"]) for slot in rule["instruments"] + rule["inputs"])
    )


def slot_rows(rule: Table) -> list[tuple[str, Table]]:
    return [("slot:" + slot["slot"], slot) for slot in rule["instruments"] + rule["inputs"]]


def covered_roles(catalog: Catalog, rule: Table) -> dict[str, tuple[Variant, ...]]:
    roles: dict[str, tuple[Variant, ...]] = {
        name: catalog.match(slot["where"], portable=True) for name, slot in slot_rows(rule)
    }
    if "subject" in rule:
        roles["subject"] = catalog.match(rule["subject"])
    target = rule.get("target", {})
    if "where" in target:
        verb = catalog.vocabulary.verbs[rule["trigger"].partition(":")[2]]
        component = verb["target"].get("class")
        roles["target"] = tuple(
            v for v in catalog.match(target["where"]) if not component or component in v.components
        )
    return roles
