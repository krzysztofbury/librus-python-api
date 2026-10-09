# Module unavailable

`ModuleUnavailableError` (`ErrorKind.MODULE_UNAVAILABLE`, `module_unavailable`)
means the requested module is not included in the school's Synergia product
variant. It is distinct from a school administrator disabling a view and from
unsupported parser markup.

The 2026-10-08 observation recorded a redirect to `/modul_niedostepny`, the
heading `Brak dostępu` and the notice:

> Ten moduł nie jest dostępny w wykorzystywanym przez szkołę wariancie rozwiązania LIBRUS Synergia.

The shared read response validator recognizes only that exact path on the
configured Synergia origin, from a response on that origin, without userinfo,
query or fragment. It does not follow the redirect, reauthenticate or replay
the read. Other redirects retain their existing access-denied/login-expiry
classification. The same fixed notice in a page-level warning box produces the
same typed outcome through `PAGE_NOTICES`; arbitrary body text is not searched.

Original offline fixtures exercise the shared HTML notice boundary and real
HTTP redirects, including foreign origins and near-miss paths. This change
introduces no request to the unavailable module. Live-check expectations map
the typed kind to `unavailable` rather than an empty successful collection.
