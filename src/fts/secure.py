import ssl
import socket
import hashlib
import os
import json
import datetime
from datetime import timezone
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from .config import (
    CERT_FILE,
    KEY_FILE,
    FINGERPRINT_FILE,
)


# --------------------------
# Helpers for fingerprints
# --------------------------

def get_fingerprint(cert_der: bytes) -> str:
    """Return SHA256 fingerprint of DER-encoded cert."""
    return hashlib.sha256(cert_der).hexdigest()

def load_known_fingerprints():
    if os.path.exists(FINGERPRINT_FILE):
        with open(FINGERPRINT_FILE, "r") as f:
            return json.load(f)
    return {}

def save_known_fingerprints(fps):
    with open(FINGERPRINT_FILE, "w") as f:
        json.dump(fps, f, indent=2)

# --------------------------
# Server side
# --------------------------

def generate_self_signed_cert(cert_file=CERT_FILE, key_file=KEY_FILE):
    """Generate a self-signed TLS certificate if missing or expired. Reuses existing key."""
    # If both cert and key exist, check expiration
    if os.path.exists(cert_file) and os.path.exists(key_file):
        try:
            with open(cert_file, "rb") as f:
                cert_pem = f.read()
            cert = x509.load_pem_x509_certificate(cert_pem)
            now = datetime.datetime.now(timezone.utc)  # timezone-aware UTC
            if cert.not_valid_after_utc > now:
                # Certificate still valid
                return False
            else:
                print(f"Certificate expired on {cert.not_valid_after_utc}, regenerating...")
        except Exception as e:
            print(f"Failed to read existing certificate: {e}, regenerating...")

    # Load or generate private key
    if os.path.exists(key_file):
        with open(key_file, "rb") as f:
            key = serialization.load_pem_private_key(f.read(), password=None)
    else:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        with open(key_file, "wb") as f:
            f.write(key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            ))
        os.chmod(key_file, 0o600)

    # Generate new self-signed certificate
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
        .not_valid_before(datetime.datetime.utcnow())
        .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    with open(cert_file, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    return True


def get_server_context():
    """Return an SSLContext configured for server use, regenerating cert if expired."""
    generate_self_signed_cert()  # will regenerate if expired
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=CERT_FILE, keyfile=KEY_FILE)
    return context


def wrap_server_socket():
    """Return an SSL-wrapped server socket (blocking, ready to accept)."""
    context = get_server_context()
    return context

# --------------------------
# Client side (TOFU)
# --------------------------

def connect_with_tofu(server_host, server_port, logger):
    """Connect to a TLS server using TOFU (Trust On First Use)."""
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE  # do manual verification

    raw_sock = socket.create_connection((server_host, server_port))
    ssock = context.wrap_socket(raw_sock, server_hostname=server_host)

    # Get server certificate in DER form
    der_cert = ssock.getpeercert(binary_form=True)
    fingerprint = get_fingerprint(der_cert)

    # Load known fingerprints
    known = load_known_fingerprints()

    if server_host not in known:
        logger.info(f"[TOFU] First connection to {server_host}, trusting cert {fingerprint}")
        known[server_host] = fingerprint
        save_known_fingerprints(known)
    else:
        if known[server_host] != fingerprint:
            ssock.close()
            raise ssl.SSLError(
                f"Server certificate for {server_host} changed!\n"
                f"Expected {known[server_host]}, got {fingerprint}"
            )
        else:
            logger.info(f"[TOFU] Verified pinned certificate {fingerprint}")

    return ssock
