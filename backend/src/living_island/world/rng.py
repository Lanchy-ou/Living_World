"""The only authoritative random stream, used by completion settlement."""

MASK = 0xFFFFFFFF
DOMAIN = 1 << 32


def xorshift32(state: int) -> int:
    state ^= (state << 13) & MASK
    state ^= state >> 17
    state ^= (state << 5) & MASK
    return state & MASK


def shuffle[T](items: list[T], state: int) -> int:
    for index in range(len(items) - 1, 0, -1):
        size = index + 1
        limit = DOMAIN - DOMAIN % size
        state = xorshift32(state)
        while state >= limit:
            state = xorshift32(state)
        swap = state % size
        items[index], items[swap] = items[swap], items[index]
    return state
