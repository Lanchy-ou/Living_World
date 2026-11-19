"""Entity definitions and the finite set of bindings used by static proofs."""

from dataclasses import dataclass
from typing import Any

from .schema import (
    TERRAINS,
    Pair,
    Table,
    array,
    boolean,
    fields,
    identifier,
    integer,
    require,
    table,
    term,
)
from .vocabulary import COMPONENTS, Vocabulary, descriptor, property_value

STATE_COMPONENT = {
    "store.count": "store",
    "store.free": "store",
    "container.used": "container",
    "container.free": "container",
    "durability.wear": "durability",
    "durability.left": "durability",
    "fuel.ticks_left": "fuel",
    "process.work_done": "process",
}
MUTABLE = {"durability.wear", "fuel.ticks_left", "process.work_done"}


def state_component(field: object, archetypes: dict[str, Table], path: str) -> str | None:
    if isinstance(field, str) and field.startswith("container.count:"):
        term(field.partition(":")[2], archetypes, path)
        return "container"
    if field in ("quantity", "age"):
        return None
    return STATE_COMPONENT[term(field, STATE_COMPONENT, path)]


@dataclass(frozen=True)
class Variant:
    pair: Pair
    properties: Table
    components: Table


@dataclass
class Catalog:
    vocabulary: Vocabulary
    materials: dict[str, Table]
    archetypes: dict[str, Table]
    instances: dict[str, Table]
    variants: list[Variant]

    def property_table(self, value: object, path: str, *, apparent: bool = False) -> Table:
        props = table(value, path)
        for key, val in sorted(props.items()):
            prop = self.vocabulary.properties[term(key, self.vocabulary.properties, path)]
            require(prop["domain"] != "count", "BAD_SHAPE", path, "count is observed state")
            require(
                not apparent or prop["observability"] != "on_use",
                "BAD_SHAPE",
                path,
                "on_use properties have no apparent value",
            )
            property_value(val, prop["domain"], path)
        return props

    def predicate(self, value: object, path: str) -> Table:
        pred = table(value, path)
        for key, val in sorted(pred.items()):
            if key in ("archetype", "material", "has_component"):
                choices = {
                    "archetype": self.archetypes,
                    "material": self.materials,
                    "has_component": COMPONENTS,
                }
                term(val, choices[key], path)
            elif key in self.vocabulary.properties:
                require(
                    self.vocabulary.properties[key]["domain"] == "bool",
                    "BAD_SHAPE",
                    path,
                    "only bool properties take an exact predicate",
                )
                boolean(val, path)
            else:
                prop, _, suffix = key.rpartition("_")
                term(prop, self.vocabulary.properties, path)
                require(
                    suffix in ("min", "max")
                    and self.vocabulary.properties[prop]["domain"] == "scale",
                    "BAD_SHAPE",
                    path,
                    f"invalid scale predicate {key}",
                )
                integer(val, path, 0, 5)
        return pred

    def ordinary(self, archetype: str, material: str | None) -> Table:
        return {
            **{
                key: prop["default"]
                for key, prop in self.vocabulary.properties.items()
                if "default" in prop
            },
            **self.materials.get(material or "", {}).get("properties", {}),
            **self.archetypes[archetype]["properties"],
        }

    def add_variant(self, variant: Variant) -> bool:
        if variant in self.variants:
            return False
        self.variants.append(variant)
        return True

    def match(self, pred: Table, *, portable: bool = False) -> tuple[Variant, ...]:
        return tuple(
            variant
            for variant in self.variants
            if (not portable or "portable" in variant.components) and matches(pred, variant)
        )


def matches(pred: Table, variant: Variant) -> bool:
    for key, expected in pred.items():
        if key == "archetype":
            ok = variant.pair[0] == expected
        elif key == "material":
            ok = variant.pair[1] == expected
        elif key == "has_component":
            ok = expected in variant.components
        elif key.endswith("_min") and key not in variant.properties:
            ok = variant.properties[key[:-4]] >= expected
        elif key.endswith("_max") and key not in variant.properties:
            ok = variant.properties[key[:-4]] <= expected
        else:
            ok = variant.properties[key] == expected
        if not ok:
            return False
    return True


def component(catalog: Catalog, key: str, data: object, path: str, *, complete: bool) -> Table:
    static, dynamic = COMPONENTS[key]
    cfg = fields(
        data, path, static if complete else "", dynamic if complete else f"{static} {dynamic}"
    )
    for field, val in sorted(cfg.items()):
        if field == "accepts":
            catalog.predicate(val, path)
        elif field == "archetype":
            arch = catalog.archetypes[term(val, catalog.archetypes, path)]
            require(
                "portable" in arch.get("components", {}),
                "BAD_SHAPE",
                path,
                "store must hold a portable archetype",
            )
        elif field in ("blocks_movement", "opaque"):
            boolean(val, path)
        else:
            integer(val, path, 1 if field in ("slots_per_unit", "work_required") else 0)
    if complete:
        for field in dynamic.split():
            cfg.setdefault(field, 0)
    for field, maximum in (
        ("count", "capacity"),
        ("wear", "max_wear"),
        ("work_done", "work_required"),
    ):
        if field in cfg and maximum in cfg:
            integer(cfg[field], path, 0, cfg[maximum])
    return cfg


def build_catalog(vocab: Vocabulary, pack: Table) -> Catalog:
    catalog = Catalog(vocab, pack["material"], pack["archetype"], pack["instance"], [])
    for key, row in catalog.materials.items():
        fields(row, key, "id", "properties apparent")
        for name in ("properties", "apparent"):
            catalog.property_table(row.setdefault(name, {}), key, apparent=name == "apparent")
    for key, row in catalog.archetypes.items():
        fields(row, key, "id kind stackable", "material matter properties components observe")
        term(row["kind"], ("item", "structure", "process", "feature"), key)
        boolean(row["stackable"], key)
        if "material" in row:
            term(row["material"], catalog.materials, key)
        matter = table(row.setdefault("matter", {}), key)
        for name, amount in sorted(matter.items()):
            term(name, vocab.matter_classes, key)
            integer(amount, key, 0)
        catalog.property_table(row.setdefault("properties", {}), key)
        components = table(row.setdefault("components", {}), key)
        require(
            "process" not in components or "container" in components,
            "BAD_SHAPE",
            key,
            "a process requires a container",
        )
        if "portable" in components:
            require(any(matter.values()), "BAD_SHAPE", key, "portable archetype has no matter")
        for name, cfg in sorted(components.items()):
            term(name, COMPONENTS, key)
            component(catalog, name, cfg, key, complete=False)
            for field in COMPONENTS[name][1].split():
                cfg.setdefault(field, 0)
        observed = set()
        for row_field in array(row.setdefault("observe", []), key):
            fields(row_field, key, "field as")
            name = term(row_field["as"], vocab.properties, key)
            require(
                vocab.properties[name]["domain"] == "count" and name not in observed,
                "BAD_SHAPE",
                key,
                "expected a distinct count property",
            )
            observed.add(name)
            required = state_component(row_field["field"], catalog.archetypes, key)
            require(
                required is not None and required in components,
                "BAD_SHAPE",
                key,
                "observed field requires its component",
            )
    for key, row in catalog.instances.items():
        fields(
            row,
            key,
            "id archetype at",
            "material quantity state phase_offset properties apparent tell owner_id contents",
        )
        arch_id = term(row["archetype"], catalog.archetypes, key)
        arch = catalog.archetypes[arch_id]
        if "material" in row:
            term(row["material"], catalog.materials, key)
        material = row.get("material", arch.get("material"))
        quantity = integer(row.setdefault("quantity", 1), key, 1)
        require(
            arch["stackable"] or quantity == 1,
            "BAD_SHAPE",
            key,
            "non-stackable quantity must be one",
        )
        if "owner_id" in row:
            identifier(row["owner_id"], key)
            require(not arch["stackable"], "BAD_SHAPE", key, "stackable instance has owner")
        location = fields(row["at"], key, optional="tile holder")
        require(len(location) == 1, "BAD_SHAPE", key, "expected one placement")
        if "tile" in location:
            coords = array(location["tile"], key)
            require(len(coords) == 2, "BAD_SHAPE", key, "expected two coordinates")
            for coord in coords:
                integer(coord, key, 0)
        else:
            identifier(location["holder"], key)
        overrides = table(row.setdefault("state", {}), key)
        for name in sorted(overrides):
            term(name, arch["components"], key)
            component(catalog, name, overrides[name], key, complete=False)
            static = set(COMPONENTS[name][0].split())
            declared = arch["components"][name]
            require(
                all(
                    field not in declared or overrides[name][field] == declared[field]
                    for field in static & overrides[name].keys()
                ),
                "BAD_SHAPE",
                key,
                "instance cannot change archetype static fields",
            )
        effective = {}
        for name, cfg in sorted(arch["components"].items()):
            effective[name] = component(
                catalog, name, {**cfg, **overrides.get(name, {})}, key, complete=True
            )
        row["state"] = effective
        if material is not None:
            row["material"] = material
        own = catalog.property_table(row.setdefault("properties", {}), key)
        apparent = catalog.property_table(row.setdefault("apparent", {}), key, apparent=True)
        ordinary = catalog.ordinary(arch_id, material)
        tell = array(row.setdefault("tell", []), key)
        if apparent or tell:
            require(bool(tell), "TELL_MISSING", key, "apparent override needs a tell")
            for name in tell:
                require(
                    isinstance(name, str) and name in own and name not in apparent,
                    "TELL_MISSING",
                    key,
                    "tell must be an unobscured own value",
                )
                prop = vocab.properties[name]
                require(
                    prop["observability"] != "on_use"
                    and descriptor(prop, ordinary[name]) != descriptor(prop, own[name]),
                    "TELL_MISSING",
                    key,
                    "tell must change the observable word",
                )
        table(row.setdefault("phase_offset", {}), key)
        contents = array(row.setdefault("contents", []), key)
        require(
            not contents or "container" in effective,
            "BAD_SHAPE",
            key,
            "contents require a container",
        )
        for item in contents:
            term(item, catalog.instances, key)
        catalog.add_variant(Variant((arch_id, material), {**ordinary, **own}, effective))
    for key, arch in catalog.archetypes.items():
        material = arch.get("material")
        components = arch["components"]
        if all(set(COMPONENTS[name][0].split()) <= cfg.keys() for name, cfg in components.items()):
            catalog.add_variant(
                Variant((key, material), catalog.ordinary(key, material), components)
            )
        else:
            require(
                any(v.pair[0] == key for v in catalog.variants),
                "BAD_SHAPE",
                key,
                "incomplete static fields without a placed instance",
            )
    return catalog


def validate_containers(catalog: Catalog) -> None:
    for variant in catalog.variants:
        components = variant.components
        if "portable" in components and "container" in components:
            require(
                not any(
                    "container" in candidate.components
                    for candidate in catalog.match(components["container"]["accepts"])
                ),
                "BAD_SHAPE",
                variant.pair[0],
                "portable container accepts a container",
            )


def phase_offsets(catalog: Catalog, rules: dict[str, Table]) -> None:
    for key, row in catalog.instances.items():
        offsets = row["phase_offset"]
        for rule, phase in sorted(offsets.items()):
            trigger: str = rules[term(rule, rules, key)]["trigger"]
            require(
                trigger.startswith("every:"), "BAD_SHAPE", key, "phase offsets require every rules"
            )
            integer(phase, key, 0, int(trigger.partition(":")[2]) - 1)
        row["phase_offset"] = {rule: phase for rule, phase in offsets.items() if phase}


def terrain(value: Any, path: str) -> str:
    return term(value, TERRAINS, path)


def closure(catalog: Catalog, rules: list[Table]) -> None:
    """Include materials of ordinary outputs, including transitive inheritance."""
    changed = True
    while changed:
        changed = False
        for rule in rules:
            slots = {
                slot["slot"]: catalog.match(slot["where"], portable=True)
                for slot in rule["instruments"] + rule["inputs"]
            }
            if "target" in rule and "where" in rule["target"]:
                slots["target"] = catalog.match(rule["target"]["where"])
            interruption = rule.get("on_interrupt")
            outputs = rule["outputs"] + (
                interruption.get("partial", []) if isinstance(interruption, dict) else []
            )
            for output in outputs:
                arch_from = output.get("archetype_from")
                mat_from = output.get("material_from")
                arch_ids = (
                    {v.pair[0] for v in slots[arch_from]} if arch_from else {output["archetype"]}
                )
                for arch_id in sorted(arch_ids):
                    arch = catalog.archetypes[arch_id]
                    if mat_from:
                        materials = {
                            v.pair[1]
                            for v in slots[mat_from]
                            if mat_from != arch_from or v.pair[0] == arch_id
                        }
                    else:
                        materials = {output.get("material", arch.get("material"))}
                    for material in sorted(materials, key=lambda value: value or ""):
                        cfg = arch["components"]
                        require(
                            all(
                                set(COMPONENTS[name][0].split()) <= values.keys()
                                for name, values in cfg.items()
                            ),
                            "BAD_SHAPE",
                            rule["id"],
                            "output archetype has unresolved static fields",
                        )
                        changed |= catalog.add_variant(
                            Variant((arch_id, material), catalog.ordinary(arch_id, material), cfg)
                        )
