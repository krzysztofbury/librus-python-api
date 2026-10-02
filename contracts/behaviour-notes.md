# Behaviour-note capability decision: 0.3.0.dev0

Decision: defer public behaviour-note support, default off. Do not provide an API
that fabricates populated records, silently returns an empty list on unknown markup,
or delegates to a consumer-specific parser. Consumer migration remains separately
authorized and must acknowledge this capability gap before claiming full parity.

## Evidence and provenance

- The unmodified external apix 1.5.3 package has no behaviour-note operation.
- Read-only consumer discovery identifies an ordinary candidate GET and documents
  only empty-state live evidence. Its populated parser assumptions are not an
  independent observation of populated school records. No consumer implementation,
  fixture or captured markup is copied into this library.
- The combined follow-up authorized one ordinary probe per attempt, but all three
  attempts stopped before reaching it. No new live empty or populated note evidence
  was collected, and the probe was not retried independently.

## Internal qualification boundary

The central `behaviour_notes_probe` GET and matching twenty-sixth OpenAPI operation
exist only for explicitly authorized manual discovery. An original offline loopback
case verifies the exact wire path and shared request budget; the optional full
Chromium preflight verifies structural empty-state classification. This is not a
public note capability or populated parser qualification. The probe does not retry,
send messages, mark content read, consume read-once events or alter notification state.

The manual harness accepts only its fixed destination, one probe request and the
original shared traffic/body/deadline budgets. It retains structural counts and the
fixed decision, never note values, identifiers or raw HTML. An explicit empty marker
does not qualify populated records. Unknown or contradictory structure stops.

To revisit the decision, obtain fresh account/operation/login/request authorization,
independently establish populated rendered semantics, author original parser/wire
fixtures and typed results, and separately coordinate the consumer capability impact.
