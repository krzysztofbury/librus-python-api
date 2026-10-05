# Behaviour notes (0.3.0)

Decision: no public behaviour-note read yet. It stays off until a populated
page has been observed, so the library never returns invented records or turns
an unrecognized page into an empty list.

## Evidence

- The reference client has no behaviour-note operation. The consumer's parser was written from
  assumptions about populated pages, not from an observed one.
- On 2026-10-02 the internal `behaviour_notes_probe` GET (`/uwagi`) was read live
  for both students. Each returned the explicit empty marker "Brak uwag" with no
  note table. An empty page says nothing about the populated layout.

## Probe

`behaviour_notes_probe` exists only for authorized discovery through
`scripts/live_capture.py`. It is not a public method. It shares the scheduler and
budgets, is never retried, and has no side effects. Its OpenAPI operation
documents the route.

## To enable

1. Capture a populated page with the live workflow in
   [CONTRIBUTING.md](../CONTRIBUTING.md#live-verification).
2. Write an original fixture with that structure, plus typed records and a
   parser with failing-first tests.
3. Add the public read to the shared read tables, and coordinate the MCP impact.
