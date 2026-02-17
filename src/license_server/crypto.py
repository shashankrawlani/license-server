import os
import json
import base64
from datetime import datetime, timezone
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.exceptions import InvalidSignature
from .config import settings

def generate_keypair():
    """Generates an RSA-2048 keypair if it doesn't already exist.

    The keys are saved to the paths specified in settings.PRIVATE_KEY_PATH 
    and settings.PUBLIC_KEY_PATH. If the private key already exists, 
    the function returns early without generating new keys.
    """
    if os.path.exists(settings.PRIVATE_KEY_PATH):
        return
    
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(settings.PRIVATE_KEY_PATH), exist_ok=True)
    
    # Save private key
    pem_private = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    with open(settings.PRIVATE_KEY_PATH, "wb") as f:
        f.write(pem_private)
        
    # Save public key
    pem_public = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    with open(settings.PUBLIC_KEY_PATH, "wb") as f:
        f.write(pem_public)

def load_private_key():
    """Loads the RSA private key from the filesystem.

    If the private key file does not exist, it triggers the generation 
    of a new keypair first.

    Returns:
        RSAPrivateKey: The loaded RSA private key object.
    """
    if not os.path.exists(settings.PRIVATE_KEY_PATH):
        generate_keypair()
        
    with open(settings.PRIVATE_KEY_PATH, "rb") as key_file:
        return serialization.load_pem_private_key(
            key_file.read(),
            password=None,
        )

def sign_license(email: str, tier: str, expires_at: datetime) -> str:
    """Creates a signed license key string.

    The license key is a dot-separated string containing a URL-safe 
    base64-encoded JSON payload and its RSA-PSS signature.

    Args:
        email: The email address associated with the license.
        tier: The license tier (e.g., 'community', 'enterprise').
        expires_at: The expiration datetime of the license.

    Returns:
        str: The signed license key in the format '{payload}.{signature}'.
    """
    private_key = load_private_key()
    
    payload = {
        "email": email,
        "tier": tier,
        "expiry": expires_at.isoformat(),
        "issued_at": datetime.now(timezone.utc).isoformat()
    }
    payload_str = json.dumps(payload, sort_keys=True)
    
    signature = private_key.sign(
        payload_str.encode(),
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH
        ),
        hashes.SHA256()
    )
    
    # URL-safe base64 encoding without padding for a cleaner key
    b64_payload = base64.urlsafe_b64encode(payload_str.encode()).decode().rstrip("=")
    b64_sig = base64.urlsafe_b64encode(signature).decode().rstrip("=")
    
    return f"{b64_payload}.{b64_sig}"

def verify_license_local(license_key: str, public_key_pem: bytes) -> dict | None:
    """Verifies a license key locally using an RSA public key.

    This function performs offline verification of the cryptographic 
    signature to ensure the license was issued by the trusted authority 
    and has not been tampered with.

    Args:
        license_key: The dot-separated license key string to verify.
        public_key_pem: The RSA public key in PEM format (bytes).

    Returns:
        dict | None: The decoded payload if verification succeeds, 
            otherwise None.
    """
    try:
        parts = license_key.split(".")
        if len(parts) != 2:
            return None
            
        b64_payload, b64_sig = parts
        
        # Add back padding
        payload_bytes = base64.urlsafe_b64decode(b64_payload + "==" * (4 - len(b64_payload) % 4))
        signature = base64.urlsafe_b64decode(b64_sig + "==" * (4 - len(b64_sig) % 4))
        payload_str = payload_bytes.decode()
        
        public_key = serialization.load_pem_public_key(public_key_pem)
        
        public_key.verify(
            signature,
            payload_str.encode(),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        
        return json.loads(payload_str)
    except Exception:
        return None
