from admin_api.request_context import resolve_admin_client_ip


def test_forwarded_ip_used_when_bff_secret_ok():
    assert resolve_admin_client_ip(socket_ip="10.0.0.1", bff_secret_ok=True, forwarded_ip="203.0.113.7") == "203.0.113.7"


def test_socket_ip_when_secret_not_ok():
    # untrusted caller cannot spoof the client IP
    assert resolve_admin_client_ip(socket_ip="10.0.0.1", bff_secret_ok=False, forwarded_ip="203.0.113.7") == "10.0.0.1"


def test_socket_ip_when_forwarded_missing():
    assert resolve_admin_client_ip(socket_ip="10.0.0.1", bff_secret_ok=True, forwarded_ip=None) == "10.0.0.1"
    assert resolve_admin_client_ip(socket_ip="10.0.0.1", bff_secret_ok=True, forwarded_ip="") == "10.0.0.1"
