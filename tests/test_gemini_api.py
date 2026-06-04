"""Unit tests for GeminiApiAdapter."""

from unittest.mock import MagicMock, patch

from agy_swarms.adapters.gemini_api import GeminiApiAdapter
from agy_swarms.types import Caps, ErrorClass, FailureClass, NodeSpec


def _node(node_id="n1", **kw):
    base = dict(
        id=node_id,
        role="worker",
        objective="Analyze logs",
        idempotency_key=f"key-{node_id}",
        model_tier="flash_high",
    )
    base.update(kw)
    return NodeSpec(**base)


def test_gemini_api_declares_exact_accounting():
    with patch("google.genai.Client"):
        adp = GeminiApiAdapter()
        assert adp.accounting == "exact"


def test_gemini_api_capability_cover_check():
    with patch("google.genai.Client"):
        adp = GeminiApiAdapter(capabilities={"file_write", "py"})
        assert adp.covers(["file_write"])
        assert adp.covers(["file_write", "py"])
        assert not adp.covers(["browser"])


def test_gemini_api_run_success():
    # Mock Client
    mock_client = MagicMock()

    # Mock generate_content response
    mock_response = MagicMock()
    mock_response.text = '{"status": "succeeded", "result": 123}'
    mock_response.usage_metadata.prompt_token_count = 100
    mock_response.usage_metadata.candidates_token_count = 50
    mock_response.usage_metadata.thinking_token_count = 10

    mock_client.models.generate_content.return_value = mock_response

    with patch("google.genai.Client", return_value=mock_client):
        # Initialize adapter with custom model_pins
        pins = {
            "default": "gemini-3.5-flash-test",
            "escalate": "gemini-3.1-pro-test",
        }
        adp = GeminiApiAdapter(model_pins=pins)

        # Test Flash node
        node_flash = _node(model_tier="flash_high")
        envelope = adp.run(node_flash, attempt=1, reservation_id="res-123")

        assert envelope.status == "succeeded"
        assert envelope.model == "gemini-3.5-flash-test"
        assert envelope.artifact == {"status": "succeeded", "result": 123}
        assert envelope.token_usage == {
            "input": 100,
            "thinking": 10,
            "output": 50,
            "cached": 0,
            "accounting": "exact",
        }
        assert envelope.error_class == ErrorClass.NONE
        assert envelope.failure_class is None

        # Verify GenerateContentConfig generation
        mock_client.models.generate_content.assert_called_once()
        args, kwargs = mock_client.models.generate_content.call_args
        assert kwargs["model"] == "gemini-3.5-flash-test"
        assert kwargs["contents"] == "Analyze logs"
        config = kwargs["config"]
        assert config.temperature == 0.0


def test_gemini_api_run_escalate_model():
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "Just standard text output"
    mock_response.usage_metadata.prompt_token_count = 150
    mock_response.usage_metadata.candidates_token_count = 80
    del mock_response.usage_metadata.thinking_token_count  # Mock missing field
    mock_client.models.generate_content.return_value = mock_response

    with patch("google.genai.Client", return_value=mock_client):
        pins = {
            "default": "gemini-3.5-flash-test",
            "escalate": "gemini-3.1-pro-test",
        }
        adp = GeminiApiAdapter(model_pins=pins)

        # Escalate to Pro tier
        node_pro = _node(model_tier="pro", caps=Caps(max_output_tokens=500))
        envelope = adp.run(node_pro, attempt=2)

        assert envelope.status == "succeeded"
        assert envelope.model == "gemini-3.1-pro-test"
        assert envelope.artifact == {"text": "Just standard text output"}
        assert envelope.token_usage["input"] == 150
        assert envelope.token_usage["thinking"] == 0
        assert envelope.token_usage["output"] == 80

        # Verify max_output_tokens was passed inside GenerateContentConfig
        args, kwargs = mock_client.models.generate_content.call_args
        config = kwargs["config"]
        assert config.max_output_tokens == 500


def test_gemini_api_run_errors():
    # Helper to test exception mapping
    def check_error(exc_msg, expected_error, expected_failure):
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception(exc_msg)

        with patch("google.genai.Client", return_value=mock_client):
            adp = GeminiApiAdapter()
            envelope = adp.run(_node())
            assert envelope.status == "failed"
            assert envelope.error_class == expected_error
            assert envelope.failure_class == expected_failure

    check_error("API key not valid", ErrorClass.AUTH, FailureClass.DETERMINISTIC)
    check_error("deadline exceeded during call", ErrorClass.TIMEOUT, FailureClass.TRANSIENT)
    check_error("Quota limit reached", ErrorClass.BUDGET, FailureClass.BUDGET)
    check_error("failed to connect to host", ErrorClass.TRANSPORT, FailureClass.TRANSIENT)
    check_error("Some random error", ErrorClass.UNKNOWN, FailureClass.DETERMINISTIC)
