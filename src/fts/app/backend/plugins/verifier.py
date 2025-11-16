import time
import os
import hashlib
import json
from fts.app.backend.plugins.config import PUBLIC_KEY, HASHES_JSON, HASHES_SIG, ERROR_FREEZE_TIME
from fts.app.config import PLUGIN_DIR
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding


def verify_plugins(plugin_files, public_key_string=PUBLIC_KEY,
                         hashes_json_path=HASHES_JSON, sig_path=HASHES_SIG):
    # Load public key
    public_key = serialization.load_pem_public_key(public_key_string.encode())

    # Load hashes and signature
    try:
        with open(hashes_json_path, "rb") as f:
            hashes_json = f.read()
        with open(sig_path, "rb") as f:
            signature = f.read()
    except:
        print("[PLUGIN VERIFIER ERROR] Failed to locate valid plugin hashes!\nRun `fts plugins upgrade` to try again")
        time.sleep(ERROR_FREEZE_TIME)
        return []


    # Verify signature
    try:
        public_key.verify(
            signature,
            hashes_json,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
    except Exception:
        print("[PLUGIN VERIFIER ERROR] Failed to locate valid plugin hashes!\nRun `fts plugins upgrade` to try again")
        time.sleep(ERROR_FREEZE_TIME)
        return []

    # Load approved hashes
    approved_hashes = json.loads(hashes_json)

    # Check each plugin
    verified_plugins = []
    for plugin in plugin_files:
        plugin_path = os.path.join(PLUGIN_DIR, plugin)

        try:
            with open(plugin_path, "rb") as f:
                content = f.read()
                h = hashlib.sha256(content).hexdigest()

            stored_hash = approved_hashes.get(plugin)

            if stored_hash is not None and h == stored_hash:
                verified_plugins.append(plugin)

        except FileNotFoundError:
            continue

    return verified_plugins