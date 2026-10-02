"""Environment configuration tests."""

import config


def test_optional_env_normalizes_an_empty_value(monkeypatch):
    monkeypatch.setenv("PROMPTPOSEFX_TEST_OPTIONAL", "")

    assert config.optional_env("PROMPTPOSEFX_TEST_OPTIONAL") is None


def test_optional_env_preserves_a_configured_value(monkeypatch):
    monkeypatch.setenv("PROMPTPOSEFX_TEST_OPTIONAL", "https://compatible.example/v1")

    assert config.optional_env("PROMPTPOSEFX_TEST_OPTIONAL") == "https://compatible.example/v1"


def test_csv_env_uses_trimmed_non_empty_values(monkeypatch):
    monkeypatch.setenv(
        "PROMPTPOSEFX_TEST_ORIGINS",
        " http://localhost:5200, ,http://127.0.0.1:5200 ",
    )

    assert config.csv_env("PROMPTPOSEFX_TEST_ORIGINS", ("fallback",)) == (
        "http://localhost:5200",
        "http://127.0.0.1:5200",
    )


def test_public_server_defaults_are_local_only():
    assert config.SERVER_HOST == "127.0.0.1"
    assert config.SERVER_PORT == 5800
    assert config.CORS_ORIGINS == (
        "http://localhost:5200",
        "http://127.0.0.1:5200",
    )
