import base64

from botocore.signers import CloudFrontSigner
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


def cf_b64(data: bytes):
    return (
        base64.b64encode(data)
        .replace(b"+", b"-")
        .replace(b"=", b"_")
        .replace(b"/", b"~")
    )


class Signer:
    def __init__(self, private_key_pem: str, key_id: str):
        self.private_key = serialization.load_pem_private_key(
            private_key_pem.encode("utf-8"),
            password=None,
            backend=default_backend(),
        )
        self.key_id = key_id
        self.cf_signer = CloudFrontSigner(self.key_id, self.rsa_sign)

    def rsa_sign(self, message):
        return self.private_key.sign(
            message, padding.PKCS1v15(), hashes.SHA1()
        )

    def cookies_for_policy(self, append, **kwargs):
        policy = self.cf_signer.build_policy(**kwargs).encode("utf-8")
        signature = self.cf_signer.rsa_signer(policy)

        policy_b64 = cf_b64(policy).decode("utf-8")
        signature_b64 = cf_b64(signature).decode("utf-8")

        out = []
        out.append("CloudFront-Key-Pair-Id=%s%s" % (self.key_id, append))
        out.append("CloudFront-Policy=%s%s" % (policy_b64, append))
        out.append("CloudFront-Signature=%s%s" % (signature_b64, append))

        return out
