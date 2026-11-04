"""
Utility script to generate VAPID public and private keys for Web Push.
Run:
    python scripts/generate_vapid_keys.py
"""
import base64
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

def main():
    # SECP256R1 (NIST P-256) is required for Web Push VAPID
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()

    # Raw 32-byte big-endian private key
    private_num = private_key.private_numbers().private_value
    private_bytes = private_num.to_bytes(32, byteorder="big")
    private_key_b64 = base64.urlsafe_b64encode(private_bytes).decode("utf-8").rstrip("=")

    # Uncompressed 65-byte point (0x04 || X || Y)
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint
    )
    public_key_b64 = base64.urlsafe_b64encode(public_bytes).decode("utf-8").rstrip("=")

    print("=" * 60)
    print("VAPID Keys Generated Successfully!")
    print("=" * 60)
    print("\nCopy these values into your .env file:\n")
    print(f"VAPID_PUBLIC_KEY={public_key_b64}")
    print(f"VAPID_PRIVATE_KEY={private_key_b64}")
    print("=" * 60)

if __name__ == "__main__":
    main()
