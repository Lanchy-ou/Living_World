"""Declared island itinerary. Supplies are gathered from the unchanged starter placements."""

from dataclasses import dataclass

from living_island.world.v2.protocol import Action

type Point = tuple[int, int]
BENCH = (38, 31)  # Grass adjacent to the spring and clay bank.
SITE = (39, 31)
WOOD = (46, 31)
START = {"ella": (29, 25), "mia": (36, 43), "ryan": (13, 32)}


@dataclass(frozen=True)
class Step:
    label: str
    action: Action
    verb: str | None = None
    target: str | Point | None = None
    tools: tuple[str, ...] = ()
    items: tuple[tuple[str, int], ...] = ()
    quantity: int = 1


def walk(*points: Point) -> list[Step]:
    return [Step("walk", "move_to", target=point) for point in points]


def gather(store: str, count: int = 1) -> list[Step]:
    return [Step("hand harvest", "act", "gather", store)] * count


def collect(item: str, quantity: int = 1) -> Step:
    return Step("collect " + item, "pick_up", target=item, quantity=quantity)


def drop(item: str, quantity: int = 1, *, at: str | Point = BENCH) -> Step:
    return Step("deliver " + item, "drop", target=at, items=((item, quantity),))


def twist(fibre: str) -> Step:
    return Step("twist " + fibre, "act", "combine", items=((fibre, 3),))


def bind(cord: str) -> Step:
    return Step(
        "bind " + cord, "act", "combine", items=(("sharp_flake", 1), ("branch", 1), (cord, 1))
    )


SLEEP = Step("sleep comparison", "act", "sleep")
DRINK = Step("drink at spring", "act", "drink")
WORK = Step("work on site", "contribute", target="shelter_site")

ELLA = [
    *gather("flint_scatter_01"),
    *walk((32, 25), (36, 25), (35, 28), (37, 29)),
    *gather("stone_outcrop_01"),
    Step("knap", "act", "strike", "flint_nodule", ("stone",)),
    *walk(BENCH),
    drop("sharp_flake"),  # No equal held stack when the head is recreated.
    *walk((42, 31), WOOD),
    *gather("deadwood_01"),
    *walk((42, 31), BENCH),
    Step("nap while the vine is in transit", "act", "sleep"),
    collect("vine", 3),
    twist("vine"),
    bind("cord:vine"),
    collect("grass_tuft", 3),
    twist("grass_tuft"),
    bind("cord:grass"),
    *walk((42, 31), WOOD),
    Step("axe harvest", "act", "cut", "deadwood_01", ("stone_axe",)),
    *walk((42, 31), BENCH),
    drop("stone_axe"),
    drop("branch", 2, at=(38, 32)),
    collect("sharp_flake"),
    *gather("clay_bank_01", 2),
    collect("grass_tuft"),
    DRINK,
    Step(
        "light two branches",
        "act",
        "light",
        "woodpile",
        ("sharp_flake", "stone"),
        (("grass_tuft", 1),),
    ),
    Step("shape pot", "act", "combine", items=(("clay_lump", 2),)),
    drop("unfired_pot", at="campfire"),
    collect("clay_pot"),
    Step("first fill", "act", "fill", "clay_pot"),
    Step("full pot", "act", "fill", "clay_pot"),
    Step("drink serving", "act", "drink", tools=("clay_pot",)),
    drop("clay_pot"),
    drop("stone"),
    drop("sharp_flake"),
    Step("mark grass site", "act", "build", SITE),
    collect("branch", 4),
    drop("branch", 4, at="shelter_site"),
    collect("grass_tuft", 4),
    drop("grass_tuft", 4, at="shelter_site"),
    collect("vine", 3),
    twist("vine"),
    drop("cord:vine", at="shelter_site"),
    WORK,
    collect("cord:vine"),
    drop("cord:vine", at=(38, 32)),
    collect("grass_tuft", 3),
    twist("grass_tuft"),
    drop("cord:grass", at="shelter_site"),
    WORK,
    SLEEP,
]

# The watcher delivers both lots of vine before Ella can start the deceptive bind.
MIA = [
    SLEEP,
    *gather("vine_tangle_02", 3),
    *walk((36, 41), (40, 39), (43, 36), (46, 32), (46, 28), (47, 26)),
    *gather("vine_tangle_01", 3),
    *walk((46, 28), (46, 31), (42, 31), BENCH),
    drop("vine", 6),
    DRINK,
    WORK,
]

RYAN = [
    SLEEP,
    *walk((18, 32), (22, 35), (26, 37), (30, 35)),
    *gather("grass_patch_01", 6),
    *walk((34, 33), BENCH),
    drop("grass_tuft", 6),
    DRINK,
    *walk((40, 35)),
    *gather("grass_patch_02", 6),
    *walk(BENCH),
    drop("grass_tuft", 6),
    *walk((34, 30), (32, 26), (31, 23)),
    *gather("deadwood_02", 4),
    *walk((32, 26), (34, 30), BENCH),
    drop("branch", 4),
    DRINK,
    WORK,
]
ROUTES = {"ella": ELLA, "mia": MIA, "ryan": RYAN}
