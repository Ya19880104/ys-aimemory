"""Create an operator-supplied password hash without putting plaintext in argv."""
import base64
import getpass
import hashlib
import hmac
import secrets


def hash_password(password: str) -> str:
    if not 10 <= len(password) <= 1024:
        raise ValueError('Use a password of 10–1024 characters')
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=32768, r=8, p=1, maxmem=64 * 1024 * 1024)
    return 'scrypt$32768$8$1$' + base64.urlsafe_b64encode(salt).decode() + '$' + base64.urlsafe_b64encode(digest).decode()


def valid_hash(value: str) -> bool:
    try:
        algo, n, r, p, salt, digest = value.split('$')
        return (algo, n, r, p) == ('scrypt', '32768', '8', '1') and len(base64.b64decode(salt, altchars=b'-_', validate=True)) == 16 and len(base64.b64decode(digest, altchars=b'-_', validate=True)) == 64
    except (ValueError, TypeError):
        return False


def verify_password(password: str, encoded: str) -> bool:
    if not valid_hash(encoded) or len(password) > 1024:
        return False
    _, _, _, _, salt, expected = encoded.split('$')
    actual = hashlib.scrypt(password.encode(), salt=base64.urlsafe_b64decode(salt), n=32768, r=8, p=1, maxmem=64 * 1024 * 1024)
    return hmac.compare_digest(actual, base64.urlsafe_b64decode(expected))


if __name__ == '__main__':
    first = getpass.getpass('New dashboard password (10+ characters): ')
    if first != getpass.getpass('Confirm password: '):
        raise SystemExit('Passwords did not match')
    print(hash_password(first))
