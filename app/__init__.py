"""app — FastAPI modüler monolit (generation / grounding / inventory / auth sınırları).

legal_core saf çekirdeği bu katmandan IO (Postgres repo'ları, model provider, HTTP)
ile sarmalanır. Modüller birbirini doğrudan değil arayüzlerle çağırır; ileride
mikroservise ayrıştırma mekaniktir.
"""
