from unittest.mock import patch, MagicMock
from decrypt.ai import decode_response
from google.genai.errors import APIError


def make_chunk(text):
	chunk = MagicMock()
	chunk.text = text
	return chunk





class TestDecodeResponseFallback:
	@patch("decrypt.ai._retry_request")
	def test_happy_path_yields_chunks_from_first_model(self, mock_retry, mock_client):
		mock_retry.return_value = [make_chunk("feat"), make_chunk(": add auth")]
		result = list(decode_response(client=mock_client, short_text="add auth", mode="commit", target_lang="English"))
		assert result == ["feat", ": add auth"]
		mock_retry.assert_called_once()
		assert mock_client.chats.create.call_args.kwargs["model"] == "gemini-2.5-flash-lite"

	@patch("decrypt.ai._retry_request")
	def test_first_model_fails_falls_back_to_second(self, mock_retry, mock_client):
		error = APIError(code=503, response_json={"error": {"message": "unavailable"}}, response=MagicMock())
		mock_retry.side_effect = [error, [make_chunk("fix: bug")]]
		result = list(decode_response(client=mock_client, short_text="fix bug", mode="commit", target_lang="English"))
		assert result == ["fix: bug"]
		assert mock_retry.call_count == 2

	@patch("decrypt.ai._retry_request")
	def test_both_models_fail_yields_red_error_message(self, mock_retry, mock_client):
		error = APIError(code=429, response_json={"error": {"message": "quota exceeded"}}, response=MagicMock())
		mock_retry.side_effect = [error, error]
		result = list(decode_response(client=mock_client, short_text="x", mode="commit", target_lang="English"))
		joined = "".join(result)
		assert "\033[31m" in joined or "\x1b[31m" in joined
		assert "Exhaustion Limit" in joined or "quota exceeded" in joined

	@patch("decrypt.ai._retry_request")
	def test_non_critical_api_error_does_not_fallback(self, mock_retry, mock_client):
		error = APIError(code=400, response_json={"error": {"message": "bad request"}}, response=MagicMock())
		mock_retry.side_effect = [error]
		result = list(decode_response(client=mock_client, short_text="x", mode="commit", target_lang="English"))
		assert mock_retry.call_count == 1
		assert len(result) > 0
		assert "bad request" in result[0] or "400" in str(result[0])


class TestDecodeResponseConfig:
	@patch("decrypt.ai._retry_request")
	def test_correct_prompt_config(self, mock_retry, mock_client):
		mock_retry.return_value = [make_chunk("привет, как дела")]
		list(decode_response(client=mock_client, short_text="прв кк дл", mode="slang", target_lang="Spanish"))
		assert mock_client.chats.create.called
		call_config = mock_client.chats.create.call_args.kwargs["config"]
		system_instruction = call_config.system_instruction
		assert "Spanish" in system_instruction
		assert "{target_lang}" not in system_instruction