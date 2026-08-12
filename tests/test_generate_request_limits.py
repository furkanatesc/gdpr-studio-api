"""GenerateRequest boyut sınırları (B4)."""
import pytest
from pydantic import ValidationError

from legal_core.models import GenerateRequest


def _base(**over):
    d = {"type": "aydinlatma", "fields": {}, "veriler": [], "amaclar": [], "kisiGrubu": None}
    d.update(over)
    return d


def test_kisi_grubu_too_long_rejected():
    with pytest.raises(ValidationError):
        GenerateRequest(**_base(kisiGrubu="x" * 501))


def test_veriler_too_many_items_rejected():
    with pytest.raises(ValidationError):
        GenerateRequest(**_base(veriler=["v"] * 201))


def test_veriler_item_too_long_rejected():
    with pytest.raises(ValidationError):
        GenerateRequest(**_base(veriler=["x" * 501]))


def test_fields_value_too_long_rejected():
    with pytest.raises(ValidationError):
        GenerateRequest(**_base(fields={"k": "x" * 5001}))


def test_fields_too_many_keys_rejected():
    with pytest.raises(ValidationError):
        GenerateRequest(**_base(fields={f"k{i}": "v" for i in range(51)}))


def test_within_limits_accepted():
    GenerateRequest(**_base(
        kisiGrubu="x" * 500,
        veriler=["x" * 500] * 200,
        amaclar=["y"] * 200,
        fields={f"k{i}": "v" * 5000 for i in range(50)},
    ))
