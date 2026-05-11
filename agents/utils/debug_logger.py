from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
import json

console = Console()


def _try_json(value) -> str:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return json.dumps(parsed, indent=2, ensure_ascii=False)
        except (json.JSONDecodeError, TypeError, ValueError):
            return value
    try:
        return json.dumps(value, indent=2, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


def log_llm_request(provider: str, messages):
    console.print(Panel(
        Syntax(_try_json(messages), "json", theme="monokai", word_wrap=True),
        title=f"[cyan]LLM Request >> {provider}[/cyan]",
        border_style="cyan",
        padding=(1, 2),
    ))


def log_llm_response(provider: str, response):
    console.print(Panel(
        Syntax(_try_json(response), "json", theme="monokai", word_wrap=True),
        title=f"[green]LLM Response << {provider}[/green]",
        border_style="green",
        padding=(1, 2),
    ))
