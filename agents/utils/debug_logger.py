from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
import json

console = Console()


def _normalize_messages(value):
    if not isinstance(value, list):
        return value
    normalized = []
    for item in value:
        if hasattr(item, "role") and hasattr(item, "parts"):
            parts_text = ""
            for p in item.parts:
                if hasattr(p, "text") and p.text:
                    parts_text += p.text
                elif hasattr(p, "function_call"):
                    parts_text += f"[Function Call: {p.function_call.name}]"
            normalized.append({"role": item.role, "content": parts_text})
        else:
            normalized.append(item)
    return normalized


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
    console.print(
        Panel(
            Syntax(_try_json(_normalize_messages(messages)), "json", theme="monokai", word_wrap=True),
            title=f"[cyan]LLM Request >> {provider}[/cyan]",
            border_style="cyan",
            padding=(1, 2),
        )
    )


def log_llm_response(provider: str, response):
    console.print(
        Panel(
            Syntax(_try_json(_normalize_messages(response)), "json", theme="monokai", word_wrap=True),
            title=f"[green]LLM Response << {provider}[/green]",
            border_style="green",
            padding=(1, 2),
        )
    )
