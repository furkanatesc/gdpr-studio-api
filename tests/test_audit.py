def test_get_client_ip_reads_contextvar():
    from app import observability

    token = observability._client_ip.set("203.0.113.5")
    try:
        assert observability.get_client_ip() == "203.0.113.5"
    finally:
        observability._client_ip.reset(token)


def test_get_client_ip_none_by_default():
    from app import observability

    assert observability.get_client_ip() is None
