import base64
import logging

from botocore.signers import CloudFrontSigner
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

LOG = logging.getLogger(__name__)


def cf_b64(data: bytes):
    return (
        base64.b64encode(data)
        .replace(b"+", b"-")
        .replace(b"=", b"_")
        .replace(b"/", b"~")
    )


class Signer:
    def __init__(self, private_key_pem: str = "", key_id: str = ""):
        self.private_key_pem = private_key_pem
        self.key_id = key_id
        self._private_key = None
        self._cf_signer = None

    @property
    def private_key(self):
        if self.private_key_pem and (self._private_key is None):
            self._private_key = serialization.load_pem_private_key(
                self.private_key_pem.encode("utf-8"),
                password=None,
                backend=default_backend(),
            )
        return self._private_key

    @property
    def cf_signer(self):
        if self._cf_signer is None:
            self._cf_signer = CloudFrontSigner(self.key_id, self.rsa_sign)
        return self._cf_signer

    def rsa_sign(self, message):
        return self.private_key.sign(
            message, padding.PKCS1v15(), hashes.SHA1()  # nosec
        )

    def cookies_for_policy(
        self, policy: str = "", signature: str = "", append: str = "", **kwargs
    ):
        if not policy:
            # If a policy wasn't provided we shouldn't trust the signature.
            # Build policy and sign, overwriting the signature if provided.
            LOG.debug("Building new policy for: %s", kwargs.get("resource"))
            policy = self.cf_signer.build_policy(**kwargs)

            LOG.debug("Signing policy: %s", policy)
            policy_b = policy.encode("utf-8")
            signature_b = self.cf_signer.rsa_signer(policy_b)

            policy = cf_b64(policy_b).decode("utf-8")
            signature = cf_b64(signature_b).decode("utf-8")

        out = []
        out.append("CloudFront-Key-Pair-Id=%s%s" % (self.key_id, append))
        out.append("CloudFront-Policy=%s%s" % (policy, append))
        out.append("CloudFront-Signature=%s%s" % (signature, append))

        return out
