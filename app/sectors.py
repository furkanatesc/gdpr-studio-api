"""Sektör kodları — tek kaynak (model, API, seed, web aynı listeyi kullanır)."""

from __future__ import annotations

SECTOR_LABELS: dict[str, str] = {
    "dis_klinigi": "Diş Kliniği",
    "e_ticaret": "E-Ticaret",
    "otel": "Otel / Konaklama",
    "sirket": "Genel Şirket",
    "psikoloji": "Psikoloji / Danışmanlık",
    "meslek_orgutu": "Meslek Örgütü",
}
SECTORS: tuple[str, ...] = tuple(SECTOR_LABELS)
