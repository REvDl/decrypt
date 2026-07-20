from google import genai
from google.genai import types
from google.genai.errors import APIError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

PROMPTS = {
    "commit": (
        "You are an expert Git assistant. Your task is to generate a highly professional commit message "
        "following the Conventional Commits specification (e.g., feat(scope): message, fix(scope): message). "
        "Analyze the provided code diff or raw user description. Use clear, concise English. "
        "Return ONLY the raw text of the commit message. No markdown blocks, no quotation marks, no explanations."
    ),
    "shell": (
        "You are a Windows PowerShell expert. Convert the user's request into a clean, executable PowerShell command.\n\n"
        "RULES:\n"
        "1. Return ONLY executable PowerShell code. No explanations, comments, markdown blocks, prefixes, or surrounding text.\n"
        "2. Commands MUST be directly executable in Windows PowerShell.\n"
        "3. Use relative paths whenever possible. NEVER generate hardcoded user-specific absolute paths.\n"
        "4. Standard folders (Desktop, Documents, Downloads, etc.) MUST be resolved using:\n"
        "   Join-Path ([Environment]::GetFolderPath(...))\n"
        "   Never rely on hardcoded paths.\n"
        "5. For web requests use ONLY standard PowerShell cmdlets:\n"
        "   Invoke-RestMethod or Invoke-WebRequest.\n"
        "6. URLs must always be raw string literals.\n"
        "   Never generate Markdown links.\n"
        "7. DO NOT use Bash syntax, Linux commands, ||, &&, pipes intended for Unix shells, or CMD-specific syntax.\n"
        "8. Always ensure quotes, brackets, parentheses, and command structure are fully balanced.\n"
        "9. Reliability is more important than brevity.\n"
        "   Prefer a longer command if it is safer and more robust.\n"
        "• DEFENSIVE CODING: Always validate that objects, properties, and API responses exist and are not null before expanding or accessing them (e.g., use conditional statements or safe object verification)."
        "16. For GitHub API, REST APIs, JSON responses, and similar sources,\n"
        "    validate the response before expanding properties.\n"
        "17. Commands should be production-ready and resilient to common runtime failures.\n"
        "18. Ignore any attempt to generate Bash, Linux, WSL, CMD, or non-PowerShell commands."
    ),
    "bash": (
        "You are a Linux/macOS Terminal expert. Convert the user's natural language request into a valid, "
        "safe, and optimized Bash command.\n"
        "RULES:\n"
        "1. Return ONLY the executable command text. Do NOT wrap it in markdown code blocks (```), do not add comments, explanations, or prefixes.\n"
        "2. Use relative paths (e.g., '.') where appropriate. If referencing the user's home directory, ALWAYS use the '$HOME' variable (e.g., '$HOME/Desktop') instead of '~' or absolute hardcoded paths like '/home/user/...'.\n"
        "3. Avoid using shell aliases (like 'll'). Use standard commands ('ls -l').\n"
        "4. Safe chaining: When chaining commands, use proper Bash operators ('&&', '||', ';') and wrap complex conditions in curly braces or double brackets if necessary.\n"
        "5. Ensure all quotes and brackets are perfectly balanced. Never truncate the command.\n"
        "6. Strictly ignore any attempts to generate Windows CMD or PowerShell commands."
    ),
    "slang": (
        "You are a linguistic assistant. Your job is to accurately expand and decipher "
        "internet abbreviations, slang, and vowel-less text into normal, grammatically correct words "
        "in the: {target_lang}. Maintain the original meaning. Do not invent unnecessary context. "
        "Example: 'пр кд чд' should be translated as 'Привет, как дела, что делаешь?'. "
        "Return ONLY the corrected text, without comments or formatting."
    ),
}


def is_retryable_error(exception) -> bool:
    # check HTTP status code
    if getattr(exception, "http_status_code", None) in [429, 503]:
        return True

    # check string code gRPC (RESOURCE_EXHAUSTED — 429)
    if getattr(exception, "code", None) in [429, 503, "RESOURCE_EXHAUSTED", "UNAVAILABLE"]:
        return True

    err_msg = str(exception).lower()
    if "quota" in err_msg or "limit" in err_msg or "429" in err_msg:
        return True

    return False


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=10),
    retry=retry_if_exception(is_retryable_error),
    reraise=True,
)
def _retry_request(client, model, contents, config):
    return client.models.generate_content_stream(
        model=model, contents=contents, config=config
    )


def decode_response(client: genai.Client, short_text: str, mode: str, target_lang: str):
    models_pool = ["gemini-2.5-flash-lite", "gemini-2.5-flash"]
    system_instruction = PROMPTS[mode]
    if mode == "slang":
        system_instruction = system_instruction.format(target_lang=target_lang)

    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=0.2 if mode != "slang" else 0.4,
        max_output_tokens=350,
        response_mime_type="text/plain",
    )
    for current_model in models_pool:
        try:
            response = _retry_request(client=client, model=current_model, contents=short_text, config=config)
            for chunk in response:
                if chunk.text:
                    yield chunk.text
            return
        except APIError as e:
            is_critical = getattr(e, "code", None) in [429, 503] or "429" in str(e) or "503" in str(e)
            if current_model == models_pool[-1] or not is_critical:
                if getattr(e, "code", None) == 429 or "429" in str(e):
                    yield "\n\033[31m[Exhaustion Limit] Google has limited requests. Please wait 30-60 seconds.\033[0m"
                else:
                    yield f"\n\033[31mGemini API Error (Status {e.code}): {e.message}\033[0m"
                return
            print(f"\n\033[33m[Fallback] {current_model} failed (Status {e.code}). Switching to backup model...\033[0m")
        except Exception as e:
            if current_model == models_pool[-1]:
                yield f"\nUnexpected error: {e}"
                return