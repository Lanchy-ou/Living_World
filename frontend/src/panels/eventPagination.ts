const PAGE_SIZE = 150;

export function eventPage<Event extends { tick: number }>(
  events: readonly Event[],
  tick: number,
  requestedPage?: number,
) {
  const pageCount = Math.ceil(events.length / PAGE_SIZE);
  let pageIndex = requestedPage;
  if (pageIndex === undefined) {
    const first = events.findIndex((event) => event.tick >= tick);
    pageIndex = first === -1 ? pageCount - 1 : Math.floor(first / PAGE_SIZE);
  }
  pageIndex = Math.max(0, Math.min(pageIndex, pageCount - 1));
  const start = pageIndex * PAGE_SIZE;
  return { pageIndex, pageCount, start, rows: events.slice(start, start + PAGE_SIZE) };
}
