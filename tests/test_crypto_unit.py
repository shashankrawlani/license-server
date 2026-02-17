import os
from datetime import datetime, timezone, timedelta
from license_server.crypto import generate_keypair, sign_license, verify_license_local, load_private_key
from license_server.config import settings

def test_generate_keypair(temp_keys_dir):
    """Test that keypair is generated when it doesn't exist."""
    assert not os.path.exists(settings.PRIVATE_KEY_PATH)
    assert not os.path.exists(settings.PUBLIC_KEY_PATH)
    
    generate_keypair()
    
    assert os.path.exists(settings.PRIVATE_KEY_PATH)
    assert os.path.exists(settings.PUBLIC_KEY_PATH)
    
    # Verify we can load it
    key = load_private_key()
    assert key is not None
    
    # Test that it doesn't overwrite if it exists
    with open(settings.PRIVATE_KEY_PATH, "w") as f:
        f.write("stale-key")
    
    generate_keypair()
    
    with open(settings.PRIVATE_KEY_PATH, "r") as f:
        assert f.read() == "stale-key"

def test_sign_and_verify_local(temp_keys_dir):
    """Test signing a license and verifying it locally."""
    email = "test@example.com"
    tier = "enterprise"
    expiry = datetime.now(timezone.utc) + timedelta(days=30)
    
    key = sign_license(email, tier, expiry)
    assert "." in key
    
    with open(settings.PUBLIC_KEY_PATH, "rb") as f:
        public_key_pem = f.read()
    
    decoded = verify_license_local(key, public_key_pem)
    assert decoded is not None
    assert decoded["email"] == email
    assert decoded["tier"] == tier
    # Isoformat comparison (trimming microseconds if needed, butisoformat handles it)
    assert decoded["expiry"] == expiry.isoformat()

def test_verify_license_invalid_format():
    """Test verification with malformed key formats."""
    assert verify_license_local("invalid-key", b"dummy") is None
    assert verify_license_local("part1.part2.part3", b"dummy") is None

def test_verify_license_corrupt_signature(temp_keys_dir):
    """Test verification with tampered signature."""
    email = "test@example.com"
    expiry = datetime.now(timezone.utc) + timedelta(days=30)
    key = sign_license(email, "community", expiry)
    
    payload, sig = key.split(".")
    tampered_key = f"{payload}.modifiedsig"
    
    with open(settings.PUBLIC_KEY_PATH, "rb") as f:
        public_key_pem = f.read()
        
    assert verify_license_local(tampered_key, public_key_pem) is None

def test_verify_license_invalid_public_key():
    """Test verification with wrong public key."""
    # This will raise if we try to parse junk as PEM, so we expect None per our try-except
    assert verify_license_local("part1.part2", b"not-a-key") is None
