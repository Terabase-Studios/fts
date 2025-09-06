import asyncio
import datetime
import hashlib
import json
import ssl
from datetime import timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from fts.config import CERT_FILE, KEY_FILE, FINGERPRINT_FILE


# --------------------------
# Helpers
# --------------------------

def get_fingerprint(cert_der: bytes) -> str:
    """Return SHA256 fingerprint of DER-encoded certificate."""
    return hashlib.sha256(cert_der).hexdigest()


def load_known_fingerprints() -> dict:
    path = Path(FINGERPRINT_FILE)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_known_fingerprints(fps: dict):
    path = Path(FINGERPRINT_FILE)
    path.write_text(json.dumps(fps, indent=2), encoding="utf-8")


# --------------------------
# Server side
# --------------------------

def generate_self_signed_cert(cert_file=CERT_FILE, key_file=KEY_FILE) -> bool:
    """
    Generate a self-signed TLS certificate if missing or expired.
    Returns True if a new certificate was created, False if existing cert is valid.
    """
    cert_path = Path(cert_file)
    key_path = Path(key_file)
    now = datetime.datetime.now(timezone.utc)

    # Check existing certificate
    if cert_path.exists() and key_path.exists():
        try:
            cert_pem = cert_path.read_bytes()
            cert = x509.load_pem_x509_certificate(cert_pem)
            if cert.not_valid_after_utc > now:
                return False  # Cert is still valid
            print(f"Certificate expired on {cert.not_valid_after_utc}, regenerating...")
        except Exception as e:
            print(f"Failed to read existing certificate: {e}, regenerating...")

    # Load or generate private key
    if key_path.exists():
        key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    else:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        key_bytes = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        )
        key_path.write_bytes(key_bytes)
        try:
            key_path.chmod(0o600)
        except Exception:
            pass  # Windows may not support chmod

    # Build self-signed certificate
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "CA"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, "City"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "FTS"),
        x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now())
        .not_valid_after(datetime.datetime.now() + datetime.timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return True


def get_server_context() -> ssl.SSLContext:
    """Return an SSLContext configured for server use, regenerating cert if expired."""
    generate_self_signed_cert()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=CERT_FILE, keyfile=KEY_FILE)
    return context


# --------------------------
# Client side (TOFU)
# --------------------------

class FingerprintMismatchError(Exception):
    """Raised when a TOFU certificate mismatch occurs."""


async def connect_with_tofu_async(host: str, port: int, logger):
    """
    Async TLS connection with TOFU verification.
    Returns: (reader, writer)
    """
    # Create SSL context
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE  # We'll do TOFU manually

    # Open async TLS connection
    reader, writer = await asyncio.open_connection(host, port, ssl=context, server_hostname=host)

    # Extract peer certificate
    ssl_object = writer.get_extra_info("ssl_object")
    der_cert = ssl_object.getpeercert(binary_form=True)
    fingerprint = get_fingerprint(der_cert)

    # TOFU verification
    host_port = f"{host}:{port}"
    known = load_known_fingerprints()

    if host_port not in known:
        logger.info(f"[TOFU] First connection to {host_port}, trusting cert {fingerprint[:16]}...")
        known[host_port] = fingerprint
        save_known_fingerprints(known)
    else:
        if known[host_port] != fingerprint:
            writer.close()
            await writer.wait_closed()
            raise FingerprintMismatchError(
                f"Server certificate for {host_port} changed!\n"
                f"Expected {known[host_port][:16]}..., got {fingerprint[:16]}...\n"
                f"If this is expected, run `fts trust {host}` to accept the new certificate."
            )
        else:
            logger.info(f"[TOFU] Verified pinned certificate {fingerprint[:16]}...")

    return reader, writer

def cmd_clear_fingerprint(args, logger=None):
    """
    Remove the saved fingerprint for the given host (supports host:port keying).
    """
    host_port = args.ip
    fps = load_known_fingerprints()
    keys_to_delete = [fp for fp in fps if host_port in fp]

    if keys_to_delete:
        for key in keys_to_delete:
            del fps[key]
        save_known_fingerprints(fps)
        msg = f"Cleared stored fingerprint for {host_port}"
    else:
        msg = f"No stored fingerprint found for {host_port}"

    if logger:
        logger.info(msg)
    else:
        print(msg)
