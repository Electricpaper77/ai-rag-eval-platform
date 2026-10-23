import time
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
import pytest
from saas.oidc import OIDCConfig, begin_login, consume_login_state, internal_user_key, verify_id_token

class FakeJWKS:
    def __init__(self, key): self.key=key
    def get_signing_key_from_jwt(self, token): return type("Key", (), {"key": self.key})()

def config(): return OIDCConfig("https://issuer.example","client-a","https://issuer.example/auth","https://issuer.example/jwks","client-a","https://app.example/callback")
def test_pkce_state_nonce_and_replay_rejection():
    store={}; url,state=begin_login(config(),store,now=100)
    assert "code_challenge_method=S256" in url and state in store
    consume_login_state(store,state,now=101)
    with pytest.raises(ValueError): consume_login_state(store,state,now=101)
def test_expired_state_and_token_rejected():
    store={}; _,state=begin_login(config(),store,now=100)
    with pytest.raises(ValueError): consume_login_state(store,state,now=401)
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048); token=jwt.encode({"iss":config().issuer,"sub":"s1","aud":config().audience,"iat":100,"exp":200,"nonce":"n"},key,algorithm="RS256")
    with pytest.raises(Exception): verify_id_token(token,config(),FakeJWKS(key),now=201)
def test_issuer_audience_and_identity_key_are_verified():
    c=config(); key=rsa.generate_private_key(public_exponent=65537,key_size=2048); current=int(time.time()); claims={"iss":c.issuer,"sub":"subject-1","aud":c.audience,"iat":current,"exp":current+300,"nonce":"n"}
    token=jwt.encode(claims,key,algorithm="RS256")
    assert verify_id_token(token,c,FakeJWKS(key.public_key()))["subject"] == "subject-1"
    with pytest.raises(Exception): verify_id_token(token,c,FakeJWKS(key.public_key()),expected_nonce="wrong")
    bad=jwt.encode({**claims,"iss":"https://wrong.example"},key,algorithm="RS256")
    with pytest.raises(Exception): verify_id_token(bad,c,FakeJWKS(key.public_key()))
    assert internal_user_key({"issuer":c.issuer,"subject":"subject-1","email":"changed@example"}) == "https://issuer.example|subject-1"
