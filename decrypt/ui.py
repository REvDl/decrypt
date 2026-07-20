from . import __version__

GREEN = "\033[92m"
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


def collect_stream(gen) -> str:
    """Prints each chunk as it arrives and returns the assembled full text."""
    parts = []
    for chunk in gen:
        print(chunk, end="", flush=True)
        parts.append(chunk)
    print()
    return "".join(parts)