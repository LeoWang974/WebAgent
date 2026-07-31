from app.models import ModelConfig
from app.services.agent_runs import _infer_adapter_key_from_model


def make_model(name: str, provider: str = "openai_compatible", base_url: str | None = None):
    return ModelConfig(
        user_id="user_1",
        name=name,
        provider=provider,
        base_url=base_url,
        is_default=False,
        is_available=True,
    )


def test_infer_openclaw_adapter_from_model_name():
    model = make_model("OpenClaw Agent", base_url="ws://127.0.0.1:18789")

    assert _infer_adapter_key_from_model(model) == "openclaw"


def test_infer_openclaw_adapter_from_gateway_url():
    model = make_model("Custom runtime", base_url="ws://127.0.0.1:18789")

    assert _infer_adapter_key_from_model(model) == "openclaw"


def test_infer_hermes_adapter_from_model_name():
    model = make_model("Hermes Agent", base_url="http://localhost:8642")

    assert _infer_adapter_key_from_model(model) == "hermes"
