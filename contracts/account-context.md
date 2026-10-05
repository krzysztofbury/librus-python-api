# Account context keys and 0.7 upgrade

## Public contract

`LibrusService(accounts, *, context_key: bytes, ...)` requires exactly 32 bytes.
Generate them with a cryptographic generator such as `secrets.token_bytes(32)`
once per application installation. The application supplies and stores the key;
the library does not read environment variables, create a key file or silently
generate an ephemeral key. Invalid key types/lengths fail before transport creation.
Length validation cannot prove entropy: do not use predictable strings or a
login/password-derived key.

For each configured account, the identifier is the lowercase 64-character hex
HMAC-SHA256 of UTF-8 JSON with these exact elements:

1. Domain separator `librus-python-api/account-context/v2`.
2. Configured alias.
3. Login string, exactly as supplied.
4. Synergia origin.
5. API origin.
6. Modern messages origin.

JSON uses ASCII escaping and compact comma/colon separators. The HMAC key is the
application's 32-byte context key. Password, represented student identity and
session cookies are deliberately excluded. Password rotation preserves identity;
different logins, aliases, origins or keys produce distinct identifiers. Two
accounts representing the same student remain independent security contexts.

The identifier resists offline login enumeration by someone who does not possess
the key. It remains linkable within the same application/key namespace. It is not
encryption, anonymous data or an authorization token. Applications must still
control who can request account operations. The `AccountContext.alias` field
remains plaintext, and result objects may contain personal data. Do not treat a
whole result or context as safe to disclose just because its identifier is keyed.

## Key ownership and rotation

Keep the key private and backed up with application recovery material. All
processes sharing persistent state must use the same key and configured account
bindings. Neither the key nor raw login is written by the library's stores.
Stores apply an additional store-local HMAC to context identifiers.

A lost or replaced key changes every account identifier. Do not use an empty
history under a new key as evidence that an operation was never sent. Rotation
requires an explicitly reviewed state-rebinding/migration procedure; the library
does not offer automatic key rotation. In-memory read-only applications may use a
fresh key intentionally, but their identifiers will not survive a restart.
Repository-only read-capture tools use fresh keys because they do not open durable
send/notification stores; their captures are not persistence migration material.

## Upgrade from 0.6.x

This is an intentional pre-1.0 API and persistence boundary change:

- Pass `context_key` to each service, including custom factories.
- The former unkeyed SHA-256 identifier is no longer produced. There is no
  fallback that exposes the old value.
- SQLite and neutral notification archive formats are now **3**. Old formats 1/2
  fail explicitly without changing database contents. Do not change a database's
  `user_version` manually: its account and payload bindings would still be old.
- No migration of existing stores is implemented in this release. Keep original
  stores, pending notification checkpoints and UNKNOWN/claimed send history.
  Reconcile them with the prior version before authorizing any new side effects.
  Existing users needing uninterrupted durable workflows must retain 0.6.x until
  an explicit migration and rollback procedure is qualified for their data.
- Do not reset old stores, discard UNKNOWN records, consume events again or resend
  a message merely to complete an upgrade. An empty new store is not a migration.
- `loguru_sink` is replaced by `diagnostics.logging_sink`, using standard-library
  logging. Custom sinks still use the same allowlisted `DiagnosticEvent` contract.

Offline tests exercise cross-service key stability, namespace separation,
password/login/alias/origin binding, invalid keys, durable restart/process
recovery, old-format refusal and both stores' POSIX platform gate. No live
account or persistent application data is used for release verification.
