from app.repository_store import RepositoryStore, decrypt_token, encrypt_token


def test_oauth_tokens_are_encrypted_and_reversible():
    token = "oauth-token-for-test"
    encrypted = encrypt_token(token)

    assert encrypted != token
    assert decrypt_token(encrypted) == token


def test_repository_connection_does_not_return_token(monkeypatch):
    repository = {
        "id": 123,
        "owner": "example",
        "name": "demo",
        "fullName": "example/demo",
        "defaultBranch": "main",
    }
    saved = RepositoryStore.upsert("alice", repository, "secret-token")

    assert saved == repository
    assert "github_token_encrypted" not in saved
    assert RepositoryStore.get_for_user("alice") == repository
