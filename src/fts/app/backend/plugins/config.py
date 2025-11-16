from fts.app.config import PLUGIN_DIR
import sys
import os

GITHUB_BASE = "https://raw.githubusercontent.com/Terabase-Studios/fts/refs/heads/main/"
GITHUB_PLUGIN_DIR = GITHUB_BASE+"plugins/"

ERROR_FREEZE_TIME = 3

SECURE_PLUGIN_DIR = PLUGIN_DIR+"_secure/"
os.makedirs(SECURE_PLUGIN_DIR, exist_ok=True)

SECURE = True
HASHES_JSON = os.path.join(SECURE_PLUGIN_DIR, "hashes.json")
HASHES_SIG = os.path.join(SECURE_PLUGIN_DIR, "hashes.sig")

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