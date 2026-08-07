"""VERBİS amaç + KVKK m.3 işlem kanonik sözlüklerini resmi public kaynaktan üretir.

Uydurma yasağı: kanonik listeler `sources/` snapshot'larından (resmi Kılavuz PDF /
KVKK m.3) gelir, modelin belleğinden değil. Yerel seed terimleri çapraz-doğrulanır;
çözülemeyen terim = build FAIL (sessiz kısmi çıktı yok).
"""

from __future__ import annotations

import json
from pathlib import Path

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


_HERE = Path(__file__).resolve().parent
_BACKEND = _HERE.parent.parent
_DATA_CANON = _BACKEND / "data" / "canonical"

_EXPECTED_AMAC = 53
_EXPECTED_ISLEM = 7


def seed_terms(field: str) -> list[str]:
    processes = json.loads((_BACKEND / "data" / "processes.json").read_text(encoding="utf-8"))
    terms: list[str] = []
    for row in processes:
        for t in (row.get("data", {}).get(field) or []):
            terms.append(t)
    return terms


def _load_synonyms(name: str) -> dict[str, str]:
    return json.loads((_HERE / name).read_text(encoding="utf-8"))


def _emit(field: str, source_file: str, synonyms_file: str, expected: int | None) -> None:
    lines = parse_source_lines((_HERE / "sources" / source_file).read_text(encoding="utf-8"))
    synonyms = _load_synonyms(synonyms_file)
    local = seed_terms(field)
    table = build_table(lines, synonyms, local)
    if expected is not None and len(table["canonical"]) != expected:
        raise SystemExit(
            f"{field}: kanonik sayısı {len(table['canonical'])}, beklenen {expected} — "
            f"kaynak çıkarımını doğrula (numarayı sessizce değiştirme)."
        )
    out = _DATA_CANON / f"{field}.json"
    out.write_text(
        json.dumps(table, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    print(f"{field}: {len(table['canonical'])} kanonik, {len(synonyms)} synonym -> {out.name}")


def main() -> None:
    _emit("amaclar", "kvkk_amaclar.txt", "synonyms_amac.json", _EXPECTED_AMAC)
    _emit("islem", "islem_baz_fiiller.txt", "synonyms_islem.json", _EXPECTED_ISLEM)


if __name__ == "__main__":
    main()
