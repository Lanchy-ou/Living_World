"""Check each settlement branch using captured operands and a physical debit ledger."""

from collections import Counter
from itertools import product

from .catalog import Catalog, Variant, matches, state_component
from .rule import PLACES, covered_roles, slot_rows
from .schema import Table, fail, require, table, term

type Binding = dict[str, Variant]
type Quantity = tuple[str, int]


class Branch:
    def __init__(
        self, catalog: Catalog, rule: Table, binding: Binding, *, partial: bool = False
    ) -> None:
        self.catalog = catalog
        self.rule = rule
        self.binding = binding
        self.path: str = rule["id"]
        self.actor: bool = rule["trigger"].startswith("verb:")
        self.partial = partial
        self.slots = {name: row["qty"] for name, row in slot_rows(rule)}
        self.inputs = {"slot:" + row["slot"]: row["qty"] for row in rule["inputs"]}
        self.remaining = dict(self.inputs)
        self.debits: Counter[tuple[str, str]] = Counter()
        self.credits: Counter[tuple[str, str]] = Counter()
        self.sources: Counter[str] = Counter()
        self.draws: dict[tuple[str, str], list[tuple[bool, int | None]]] = {}

    def place(self, raw: str) -> None:
        place = term(raw, PLACES, self.path, "BAD_SHAPE")
        role, _, field = place.partition(".")
        if role == "actor":
            require(self.actor, "BAD_SHAPE", self.path, "world rule has actor placement")
        elif field == "tile" and role == "target" and "target" in self.rule:
            return
        else:
            self.variant(role)
        if field in ("store", "contents"):
            self.holder(role, field)

    def variant(self, role: str) -> Variant:
        if role not in self.binding:
            fail("BAD_SHAPE", self.path, f"{role} has no entity binding")
        return self.binding[role]

    def holder(self, role: str, field: str) -> Table:
        variant = self.variant(role)
        component = "container" if field == "contents" else "store"
        require(
            component in variant.components, "BAD_SHAPE", self.path, f"{role} must have {component}"
        )
        require(
            self.slots.get(role, 1) == 1,
            "BAD_SHAPE",
            self.path,
            "multipart slots cannot identify a holder",
        )
        return table(variant.components[component], self.path)

    def fit(self, place: str, archetype: str) -> int:
        self.place(place)
        role, _, field = place.partition(".")
        require(
            field in ("store", "contents"),
            "BAD_SHAPE",
            self.path,
            "fit requires a store or contents",
        )
        holder = self.holder(role, field)
        if field == "store":
            return int(holder["capacity"]) if holder["archetype"] == archetype else 0
        cfg = self.catalog.archetypes[archetype]["components"]
        require(
            "portable" in cfg and "slots_per_unit" in cfg["portable"],
            "BAD_SHAPE",
            self.path,
            "container output must be a portable item",
        )
        return int(holder["capacity"]) // int(cfg["portable"]["slots_per_unit"])

    def quantity(self, raw: int | Table, *, arch: str = "") -> Quantity:
        if isinstance(raw, int):
            return "", raw
        ref: str = raw["of"]
        if ref.startswith("fit:"):
            require(bool(arch), "BAD_SHAPE", self.path, "debit cannot read fit")
            bound = self.fit(ref.removeprefix("fit:"), arch)
            return ("", raw["upto"]) if "upto" in raw else (ref, bound)
        role, _, field = ref.partition(".")
        if field == "quantity":
            self.variant(role)
            if role in self.slots:
                val = self.slots[role]
                return "", min(val, raw.get("upto", val))
            if not self.catalog.archetypes[self.variant(role).pair[0]]["stackable"]:
                return "", 1
        elif field == "store.count":
            self.holder(role, "store")
        else:
            fail("BAD_SHAPE", self.path, f"invalid quantity reference {ref}")
        return ("", raw["upto"]) if "upto" in raw else (ref, 1)

    def matter(self, counts: Counter[tuple[str, str]], archetype: str, amount: Quantity) -> None:
        ref, units = amount
        for matter, weight in self.catalog.archetypes[archetype]["matter"].items():
            counts[(matter, ref)] += weight * units

    def output_role(self, output: Table, key: str) -> str | None:
        name = output.get(key)
        if name == "target":
            return "target"
        return f"slot:{name}" if name is not None else None

    def output(self, output: Table) -> None:
        arch_from = self.output_role(output, "archetype_from")
        mat_from = self.output_role(output, "material_from")
        archetype = self.variant(arch_from).pair[0] if arch_from else output["archetype"]
        arch = self.catalog.archetypes[archetype]
        place: str = output["at"]
        self.place(place)
        role, _, field = place.partition(".")
        material = output.get(
            "material", self.variant(mat_from).pair[1] if mat_from else arch.get("material")
        )
        if field == "store":
            require(
                self.holder(role, field)["archetype"] == archetype,
                "BAD_SHAPE",
                self.path,
                "output disagrees with store archetype",
            )
        if field == "contents":
            cfg = self.holder(role, field)
            require(
                "portable" in arch["components"]
                and matches(
                    cfg["accepts"],
                    Variant(
                        (archetype, material),
                        self.catalog.ordinary(archetype, material),
                        arch["components"],
                    ),
                ),
                "BAD_SHAPE",
                self.path,
                "contents reject output",
            )

        raw = output["quantity"]
        amount = self.quantity(raw, arch=archetype)
        ref, units = amount
        if "source" in output:
            require(not self.partial, "BAD_SHAPE", self.path, "partial output needs input matter")
            require(
                not self.rule["trigger"].startswith("when:"),
                "BAD_SHAPE",
                self.path,
                "when rule cannot use a source",
            )
            source = term(output["source"], self.catalog_sources, self.path, "UNDECLARED_SOURCE")
            declaration = self.catalog_sources[source]
            require(
                declaration["archetype"] == archetype,
                "UNDECLARED_SOURCE",
                self.path,
                "source supplies another archetype",
            )
            require(
                not ref or ref.startswith("fit:"),
                "UNDECLARED_SOURCE",
                self.path,
                "source does not have a static upper bound",
            )
            self.sources[source] += units
            require(
                self.sources[source] <= declaration["max_per_application"],
                "UNDECLARED_SOURCE",
                self.path,
                "combined source bound exceeded",
            )
        elif arch_from is not None and arch_from == mat_from:
            require(
                not ref and arch_from in self.remaining and units <= self.remaining[arch_from],
                "CONSERVATION",
                self.path,
                "summed returns exceed consumed units of their slot",
            )
            self.remaining[arch_from] -= units
        else:
            require(
                not isinstance(raw, dict) or not raw["of"].startswith("fit:"),
                "CONSERVATION",
                self.path,
                "fit requires a declared source",
            )
            self.matter(self.credits, archetype, amount)

    def condition_minimum(self, role: str, field: str, default: int) -> int:
        result = default
        for condition in self.rule["conditions"]:
            if (
                condition["kind"] == "state"
                and condition["of"] == role
                and condition["field"] == field
            ):
                op, value = condition["op"], condition["value"]
                if op in (">", ">=", "=="):
                    result = max(result, value + (op == ">"))
        return result

    def withdraw(self, effect: Table) -> None:
        consume = effect["op"] == "consume"
        source: str = effect["of"] if consume else effect["from"]
        role, _, field = source.partition(".")
        raw = effect.get("quantity")
        if not field:
            require(
                consume and role in ("subject", "target"),
                "BAD_SHAPE",
                self.path,
                "only target or subject can be consumed directly",
            )
            archetype = self.variant(role).pair[0]
            require(
                "archetype" not in effect,
                "BAD_SHAPE",
                self.path,
                "entity consume has no archetype operand",
            )
            expected = f"{role}.quantity"
            state_field = "quantity"
            guaranteed = 0 if self.catalog.archetypes[archetype]["stackable"] else 1
            lower = self.condition_minimum(role, state_field, guaranteed)
        else:
            require(
                field == "contents"
                or (field == "store" and not consume and role in ("subject", "target")),
                "BAD_SHAPE",
                self.path,
                "invalid withdrawal source",
            )
            holder = self.holder(role, field)
            if field == "store":
                require(
                    "archetype" not in effect or holder["archetype"] == effect["archetype"],
                    "BAD_SHAPE",
                    self.path,
                    "withdrawal disagrees with store archetype",
                )
                archetype = holder["archetype"]
                expected = f"{role}.store.count"
                state_field = "store.count"
            else:
                archetype = term(effect.get("archetype"), self.catalog.archetypes, self.path)
                expected = None
                state_field = f"container.count:{archetype}"
            reserved = sum(
                qty
                for slot, qty in self.inputs.items()
                if role == "subject"
                and field == "contents"
                and self.variant(slot).pair[0] == archetype
            )
            lower = self.condition_minimum(role, state_field, reserved) - reserved
        if isinstance(raw, dict):
            require(
                raw["of"] == expected,
                "BAD_SHAPE",
                self.path,
                "withdrawal can read only its own captured count",
            )
            debit = ("", 0) if "upto" in raw else self.quantity(raw)
            draw = (True, raw.get("upto"))
        elif raw is None:
            require(not field and consume, "BAD_SHAPE", self.path, "withdrawal needs quantity")
            debit = self.quantity({"of": expected})
            draw = (True, None)
        else:
            debit = ("", raw)
            draw = (False, raw)
        key = (source, archetype)
        draws = self.draws.setdefault(key, [])
        draws.append(draw)
        # A lone captured count is safe without a lower bound, but multiple
        # withdrawals may reserve the same units unless their joint maximum fits.
        bounded = all(units is not None for _, units in draws)
        total = sum(units or 0 for _, units in draws)
        require(
            (len(draws) == 1 and draws[0][0]) or (bounded and total <= lower),
            "CONSERVATION",
            self.path,
            f"unproven joint debit on {source} for {archetype}",
        )
        if consume:
            self.matter(self.debits, archetype, debit)
        else:
            destination = effect["to"]
            self.place(destination)
            dest, _, place_field = destination.partition(".")
            if place_field == "store":
                require(
                    self.holder(dest, place_field)["archetype"] == archetype,
                    "BAD_SHAPE",
                    self.path,
                    "move disagrees with store archetype",
                )

    def validate(self, outputs: list[Table], effects: list[Table], sources: Table) -> None:
        self.catalog_sources = sources
        for effect in effects:
            if effect["op"] in ("consume", "move"):
                self.withdraw(effect)
        for output in outputs:
            self.output(output)
        for slot, qty in self.remaining.items():
            self.matter(self.debits, self.variant(slot).pair[0], ("", qty))
        for key, amount in sorted(self.credits.items()):
            require(
                amount <= self.debits[key],
                "CONSERVATION",
                self.path,
                f"branch credits exceed debits for {key[0]} ({key[1] or 'constant'})",
            )


def validate_branches(catalog: Catalog, rule: Table, sources: Table) -> None:
    roles = covered_roles(catalog, rule)
    path = rule["id"]
    failed = rule.get("chance_failed_effects", [])
    for effect in rule["effects"] + failed:
        if effect["op"] == "set_state":
            component = state_component(effect["field"], catalog.archetypes, path)
            require(
                effect["of"] in roles
                and all(component in v.components for v in roles[effect["of"]]),
                "BAD_SHAPE",
                path,
                "effect requires a component",
            )
    mode = rule.get("on_interrupt")
    partial = mode.get("partial") if isinstance(mode, dict) else None
    for output in rule["outputs"] + (partial or []):
        if "source" in output:
            term(output["source"], sources, path, "UNDECLARED_SOURCE")
            require(
                not rule["trigger"].startswith("when:"),
                "BAD_SHAPE",
                path,
                "when rule cannot use a source",
            )
    if not (
        rule["outputs"] or partial or any(e["op"] in ("move", "consume") for e in rule["effects"])
    ):
        return

    # A homogeneous assignment is sufficient to test matter budgets: mixed
    # slots have a weighted sum of the same per-unit contributions.
    for values in product(*roles.values()):
        binding = dict(zip(roles, values, strict=True))
        Branch(catalog, rule, binding).validate(rule["outputs"], rule["effects"], sources)
        if partial is not None:
            Branch(catalog, rule, binding, partial=True).validate(partial, [], sources)
