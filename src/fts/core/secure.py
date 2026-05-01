import asyncio
import datetime
import hashlib
import ipaddress
import json
import re
import socket
import ssl
import uuid
from datetime import timezone
from pathlib import Path

import psutil
from cryptography import x509
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from fts.cache import CERT_FILE, KEY_FILE, FINGERPRINT_FILE


# --------------------------
# Helpers
# --------------------------

def get_mac_address() -> str:
    """Returns the MAC address in standard format."""
    mac_num = uuid.getnode()
    mac = ':'.join(("%012x" % mac_num)[i:i + 2] for i in range(0, 12, 2))
    return mac


def get_ip_to_mac() -> dict[str, str]:
    """
    Returns a dict mapping local IPv4 addresses -> MAC addresses
    for all host network interfaces (excluding loopback).
    """
    ip_to_mac = {}

    for iface, addrs in psutil.net_if_addrs().items():
        mac = None

        # Find MAC
        for addr in addrs:
            if addr.family == psutil.AF_LINK and addr.address:
                mac = addr.address.lower()
                break

        if not mac or mac == "00:00:00:00:00:00":
            continue

        # Bind IPv4s only
        for addr in addrs:
            if addr.family == socket.AF_INET:
                ip = addr.address

                # Skip loopback + link-local junk
                if ip.startswith("127.") or ip.startswith("169.254."):
                    continue

                ip_to_mac[ip] = mac

    return ip_to_mac


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
            print(f"[FTS] TLS certificate expired ({cert.not_valid_after_utc:%Y-%m-%d}), regenerating...")
        except Exception as e:
            print(f"[FTS] Failed to read existing certificate: {e}, regenerating...")

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
        .not_valid_before(datetime.datetime.now(timezone.utc))
        .not_valid_after(datetime.datetime.now(timezone.utc) + datetime.timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
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


async def connect_with_tofu_async(host: str, port: int, logger, require_confirmation: bool = True):
    """
    Async TLS connection with TOFU verification (Trust On First Use).
    Returns: (reader, writer)
    """
    # Create SSL context
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    # Open async TLS connection
    reader, writer = await asyncio.open_connection(host, port, ssl=context, server_hostname=host)

    # --- Read MAC address from server ---
    try:
        mac_bytes = await asyncio.wait_for(reader.readline(), timeout=5.0)
        if not mac_bytes:
            raise ConnectionError("Server did not send MAC address.")
        mac_address = mac_bytes.decode().strip()
        # Very basic MAC address validation
        if not re.match(r"([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", mac_address):
            raise ValueError(f"Received invalid MAC address format: {mac_address}")
    except (asyncio.TimeoutError, ConnectionError, ValueError) as e:
        writer.close()
        await writer.wait_closed()
        raise ConnectionError(f"Failed to get MAC address from server: {e}") from e

    # Extract peer certificate
    ssl_object = writer.get_extra_info("ssl_object")
    der_cert = ssl_object.getpeercert(binary_form=True)
    fingerprint = get_fingerprint(der_cert)

    known = load_known_fingerprints()
    matched_key = mac_address  # Use MAC address as the key

    # Trust verification / first use
    if matched_key not in known:
        short_fp = fingerprint[:16]
        full_fp = fingerprint
        if require_confirmation:
            user_input = None
            logger.debug(f"User asked to verify new server {mac_address} ({short_fp}...)")
            try:
                print("\n[TOFU] First time connecting to this server.")
                print(f"Server MAC address: {mac_address}")
                print(f"Certificate SHA256 fingerprint:\n{full_fp}")
                print("\nVerify this fingerprint with the server administrator before trusting.")
                print("Type 'yes' to trust and continue, anything else to abort.")

                user_input = input("> ").strip().lower()
            except Exception as e:
                pass

            if user_input != "yes":
                writer.close()
                await writer.wait_closed()
                raise FingerprintMismatchError("User rejected unknown server certificate.")
        else:
            logger.warning("Require confirmation of new servers is disabled. Automatically trusting new server.")

        known[matched_key] = fingerprint
        save_known_fingerprints(known)

        if logger:
            logger.info(f"[TOFU] Trusted new server {mac_address} ({short_fp}...)")
    else:
        if known[matched_key] != fingerprint:
            writer.close()
            await writer.wait_closed()
            raise FingerprintMismatchError(
                f"Server certificate for {mac_address} changed!\n"
                f"Expected {known[matched_key][:16]}..., got {fingerprint[:16]}...\n"
                f"If this is expected, run `fts trust {mac_address}` to accept the new certificate."
            )
        else:
            logger.debug(f"[TOFU] Verified pinned certificate for {mac_address} ({fingerprint[:16]}...).")

    return reader, writer


def cmd_clear_fingerprint(args, logger=None):
    """
    Remove the saved fingerprint for the given MAC address.
    """
    target = args.mac

    if target == "all":
        save_known_fingerprints({})
        msg = "Cleared all stored fingerprint(s)"
        if logger:
            logger.info(msg)
        else:
            print(msg)
        return

    fps = load_known_fingerprints()

    if target in fps:
        del fps[target]
        save_known_fingerprints(fps)
        msg = f"Cleared stored fingerprint for {target}"
    else:
        msg = f"No stored fingerprint found for {target}"

    if logger:
        logger.info(msg)
    else:
        print(msg)


def is_public_network(debug: bool = False) -> bool:
    """
    Check if the machine's primary network is public.

    Returns:
        True if the primary outbound IP is globally routable (public).
        False if private, loopback, link-local, reserved, or unknown.
    """
    try:
        # Determine the IP used for outbound traffic
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))  # dummy external host
            local_ip = s.getsockname()[0]

        ip_obj = ipaddress.ip_address(local_ip)
        result = ip_obj.is_global

        if debug:
            reason = "globally routable" if result else (
                "private" if ip_obj.is_private else
                "loopback" if ip_obj.is_loopback else
                "link-local" if ip_obj.is_link_local else
                "reserved/multicast"
            )
            if result:
                print(f"Primary outbound IP: {local_ip} ({reason}) → Public: {result}")

        return result

    except Exception as e:
        if debug:
            print(f"Failed to determine network type: {e}")
        # Fail-safe: treat as non-public
        return False
