from app.grounding_options import grounding_options


def test_options_from_catalog():
    opt = grounding_options()
    assert isinstance(opt["kategoriler"], list) and opt["kategoriler"]
    assert isinstance(opt["amaclar"], list)
    assert "Kimlik" in opt["kategoriler"]
