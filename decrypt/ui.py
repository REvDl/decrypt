from . import __version__
import warnings

warnings.filterwarnings(
    "ignore",
    message=r".*Direct use of automatic function calling \(AFC\).*",
    category=UserWarning,
)


GREEN = "\033[92m"
RED = "\033[31m"
YELLOW = "\033[33m"
BOLD = "\033[1m"
DIM = "\033[2m"
RST = "\033[0m"

BANNER = f"""{GREEN}{BOLD}
 ██████╗ ███████╗ ██████╗██████╗ ██╗   ██╗██████╗ ████████╗
 ██╔══██╗██╔════╝██╔════╝██╔══██╗╚██╗ ██╔╝██╔══██╗╚══██╔══╝
 ██║  ██║█████╗  ██║     ██████╔╝ ╚████╔╝ ██████╔╝   ██║   
 ██║  ██║██╔══╝  ██║     ██╔══██╗  ╚██╔╝  ██╔═══╝    ██║   
 ██████╔╝███████╗╚██████╗██║  ██║   ██║   ██║        ██║   
 ╚═════╝ ╚══════╝ ╚═════╝╚═╝  ╚═╝   ╚═╝   ╚═╝        ╚═╝   {RST}
  {DIM}AI-powered CLI tool: Conventional Commits · Shell Commands · Slang Decoder{RST}
  {DIM}v{__version__} Author: github.com/REvDl{RST}
"""

def banner() -> None:
    print(BANNER)

def error(message: str) -> None:
    print(f"{RED}{message}{RST}")

def warning(message: str) -> None:
    print(f"{YELLOW}{message}{RST}")

def success(message: str) -> None:
    print(f"{GREEN}{message}{RST}")

def heading(message: str) -> None:
    print(f"{GREEN}{BOLD}{message}{RST}")

def dim(message: str) -> None:
    print(f"{DIM}{message}{RST}")

def collect_stream(gen) -> str:
    """Prints each chunk as it arrives and returns the assembled full text."""
    parts = []
    for chunk in gen:
        print(chunk, end="", flush=True)
        parts.append(chunk)
    print()
    return "".join(parts)