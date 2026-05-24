from fts import __version__
fts_version = __version__()
fts_release_version = ".".join(fts_version.split(".")[:2])

API_BASE = "https://api.terabasestudios.com/"
API_PLUGIN_DIR = API_BASE + f"plugins/{fts_release_version}/"
API_PLUGIN_ARGS = "?service=fts&version=v1"
API_PLUGIN_HEADERS={
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json,text/html,*/*",
    "Referer": "https://terabasestudios.com/"
}

ERROR_FREEZE_TIME = 3

SECURE = True

PUBLIC_KEY = """
-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEApogWsJ0pstOAvr2xVg/k
bbk/NJz5hgZW6iT1SaqdWKoZFMNGV2D+aHyARFG5nj2SMaNX7E6OeUTVN2hU5Xl/
sN97vE5fxcODuf6OE781/KbISuo2hRMWtbH90sKgjKjzsxk01JcgXbXM9jvKzrZ8
u8r04yrG3glbWGjqAW2tMWJcZYgrqDxSeKUxRc9aH0iZ+q2lTrGLAwJ2GkTo2NpI
5sjfQb0RO9ozjdqVH2/mzCsCRvOJrJVBqoJLWeeH61XnYHjyWrE7tGdUFjNSWwtV
zdUaRCC3Y3Y6whW7EGak3bAJj+srwtzU/1tPAidqEvlF0S7s2bNOlO03dOW2W3Oo
QQIDAQAB
-----END PUBLIC KEY-----
"""