import httpx

_UA = "Xeria-Launcher/2.504"

_client = None


def client():
    global _client
    if _client is None:
        _client = httpx.Client(
            headers={"User-Agent": _UA},
            timeout=httpx.Timeout(20.0, connect=10.0),
            follow_redirects=True,
            limits=httpx.Limits(
                max_connections=24,
                max_keepalive_connections=12,
                keepalive_expiry=30.0,
            ),
            http2=True,
        )
    return _client


def get(url, **kwargs):
    return client().get(url, **kwargs)


def post(url, **kwargs):
    return client().post(url, **kwargs)


def stream(method, url, **kwargs):
    return client().stream(method, url, **kwargs)


def close():
    global _client
    if _client is not None:
        try:
            _client.close()
        except Exception:
            pass
        _client = None
