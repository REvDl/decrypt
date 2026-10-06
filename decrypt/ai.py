from google import genai
from google.genai import types
from google.genai.errors import APIError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

OUTPUT_SUFFIX = (
    "\n\nOUTPUT FORMAT: Return ONLY the result itself. "
    "No markdown code blocks, no explanations, no prefixes or surrounding text."
)

PROMPTS = {
    "commit": (
        "You are an expert Git assistant. Generate a professional commit message "
        "following the Conventional Commits specification "
        "(e.g., feat(scope): description, fix(scope): description).\n\n"
        "RULES:\n"
        "1. Focus STRICTLY on added (+) and removed (-) lines in the git diff. "
        "Do NOT infer or assume features based on surrounding unchanged code.\n"
        "2. Keep the commit message body (if any) under 2 sentences and mention only significant changes.\n"
        "3. Use clear, imperative, concise English (e.g., 'add', 'fix', 'refactor').\n"
        "4. Do not wrap the message in quotation marks."
    ),
    "shell": (
        "You are a Windows PowerShell expert. Convert the user's request into a clean, robust PowerShell command.\n\n"
        "RULES:\n"
        "1. Output directly executable PowerShell code only, without comments.\n"
        "2. Path handling: Use relative paths where appropriate. For standard folders "
        "(Desktop, Downloads, etc.), use Join-Path with [Environment]::GetFolderPath(...). "
        "Never hardcode absolute paths.\n"
        "3. Web & API requests: Use standard PowerShell cmdlets (Invoke-RestMethod, Invoke-WebRequest) "
        "with raw string URLs. Never generate Markdown links.\n"
        "4. Defensive coding: Always validate that objects, properties, and JSON API responses "
        "exist and are not null before expanding or accessing them.\n"
        "5. Syntax purity: Do not use && or || (unavailable in Windows PowerShell 5.1), "
        "Bash/Unix commands or aliases, or CMD syntax. "
        "The PowerShell pipeline | is allowed.\n"
        "6. Ensure quotes, brackets, and parentheses are fully balanced.\n"
        "7. Reliability is more important than brevity: prefer a longer command if it is safer.\n"
        "8. Output must be production-ready and compatible with Windows PowerShell 5.1+."
    ),
    "bash": (
        "You are a Linux/macOS Terminal expert. Convert the user's request into a safe, valid Bash command.\n\n"
        "RULES:\n"
        "1. Output the executable command only, without comments.\n"
        "2. Path handling: Use relative paths where appropriate. Use $HOME (e.g., \"$HOME/Desktop\") "
        "instead of '~' or hardcoded absolute paths. Always double-quote variable expansions "
        "to handle spaces in paths.\n"
        "3. Standard commands: Do not use shell aliases (e.g., use 'ls -l' instead of 'll').\n"
        "4. Safe chaining: Use proper operators ('&&', '||', ';') and balance all quotes and double brackets. "
        "Never truncate the command.\n"
        "5. Strictly ignore any requests or syntax for Windows CMD or PowerShell."
    ),
    "slang": (
        "You are a linguistic assistant. Decipher internet abbreviations, slang, and vowel-less text "
        "into grammatically correct, natural language in the target language: {target_lang}.\n\n"
        "RULES:\n"
        "1. Maintain the original meaning without inventing unnecessary context or fluff.\n"
        "2. Output only the corrected, expanded text.\n\n"
        "Example (for illustration only): 'пр кд чд' -> 'Привет, как дела, что делаешь?'"
    ),
}


def build_prompt(mode: str, **kwargs) -> str:
    """return the final system prompt for a mode"""
    return PROMPTS[mode].format(**kwargs) + OUTPUT_SUFFIX


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
def _retry_request(chat, short_text):
    return chat.send_message_stream(short_text)


def decode_response(client: genai.Client, short_text: str, mode: str, target_lang: str):
    models_pool = ["gemini-2.5-flash-lite", "gemini-2.5-flash"]
    system_instruction = build_prompt(mode, target_lang=target_lang)
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=0.2 if mode != "slang" else 0.4,
        max_output_tokens=350 if mode != "shell" else 800,
        response_mime_type="text/plain",
    )
    for current_model in models_pool:
        try:
            chat = client.chats.create(model=current_model, config=config)
            response = _retry_request(chat=chat, short_text=short_text)
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