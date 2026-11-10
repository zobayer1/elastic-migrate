import hashlib

from esmigrate.commons import make_sha1


def test_make_sha1_returns_raw_digest_of_utf8_text():
    """Test fails if make_sha1 does not return the raw SHA-1 digest of the UTF-8 encoded text"""
    assert make_sha1("").hex() == "da39a3ee5e6b4b0d3255bfef95601890afd80709"
    assert make_sha1("zoë") == hashlib.sha1("zoë".encode()).digest()


def test_make_sha1_honours_requested_encoding():
    """Test fails if make_sha1 ignores the requested encoding"""
    assert make_sha1("zoë", encoding="latin-1") == hashlib.sha1("zoë".encode("latin-1")).digest()
