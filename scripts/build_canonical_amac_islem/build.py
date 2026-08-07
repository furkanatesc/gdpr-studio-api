"""VERBİS amaç + KVKK m.3 işlem kanonik sözlüklerini resmi public kaynaktan üretir.

Uydurma yasağı: kanonik listeler `sources/` snapshot'larından (resmi Kılavuz PDF /
KVKK m.3) gelir, modelin belleğinden değil. Yerel seed terimleri çapraz-doğrulanır;
çözülemeyen terim = build FAIL (sessiz kısmi çıktı yok).
"""

from __future__ import annotations

from legal_core.normalize import norm


def parse_source_lines(text: str) -> list[str]:
    out: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        out.append(line)
    return out


def resolve(term: str, norm_canonical: dict[str, str], synonyms: dict[str, str]) -> str | None:
    n = norm(term)
    if not n:
        return None
    if n in norm_canonical:
        return norm_canonical[n]
    ns = {norm(k): v for k, v in synonyms.items()}
    if n in ns:
        return ns[n]
    return None


def build_table(
    canonical_lines: list[str],
    synonyms: dict[str, str],
    local_terms: list[str],
) -> dict:
    canonical = sorted(set(canonical_lines), key=lambda s: norm(s))
    norm_canonical = {norm(c): c for c in canonical}

    for target in synonyms.values():
        if norm(target) not in norm_canonical:
            raise ValueError(f"synonym hedefi kanonik değil: {target!r}")

    unresolved = [
        t for t in local_terms if resolve(t, norm_canonical, synonyms) is None
    ]
    if unresolved:
        raise ValueError(f"çözülemeyen yerel terim(ler): {sorted(set(unresolved))}")

    return {"canonical": canonical, "synonyms": dict(synonyms)}
