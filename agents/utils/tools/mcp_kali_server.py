#!/env/bin/env python3

# /agents/utils/tools/mcp_kali_server.py
# KaliGPT client for Kali Linux Tools API Server v0.2.1
# REST API at 192.168.1.55:5000
# Last updated: 10 May 2026


import requests


KALI_SERVER_URL = "http://192.168.1.55:5000"

KALI_REQUEST_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
}


def check_mcp_connection(timeout: int = 10) -> bool:
    """
    Check if the Kali Linux Tools API Server is reachable.
    """
    try:
        resp = requests.get(f"{KALI_SERVER_URL}/health", timeout=timeout)
        return resp.status_code == 200 and resp.json().get("status") == "healthy"
    except requests.RequestException:
        return False


def list_mcp_tools(timeout: int = 10) -> list:
    """
    List available Kali Linux tools from the server.
    Returns a list of tool names that are installed and ready.
    """
    try:
        resp = requests.get(f"{KALI_SERVER_URL}/health", timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        tools_status = data.get("tools_status", {})
        return [{"name": name, "available": available} for name, available in tools_status.items()]
    except requests.RequestException as e:
        return [{"error": str(e)}]


def call_mcp_tool(tool_name: str, arguments: dict = None, timeout: int = 120) -> dict:
    """
    Execute a Kali Linux tool on the remote server.

    Runs a tool like nmap, nikto, sqlmap, gobuster, etc. on the Kali server
    at 192.168.1.55. Use list_mcp_tools to discover available tools.

    Args:
        tool_name: Name of the tool to run (e.g. "nmap", "nikto", "sqlmap")
        arguments: Dictionary of arguments/flags for the tool.
                   Common keys: target, flags, wordlist, ports, etc.
        timeout: Request timeout in seconds (default 120, max 300)

    Returns:
        dict with stdout, stderr, return_code, success, timed_out
    """
    if arguments is None:
        arguments = {}

    try:
        resp = requests.post(
            f"{KALI_SERVER_URL}/api/tools/{tool_name}",
            json=arguments,
            headers=KALI_REQUEST_HEADERS,
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        return {"success": False, "stdout": "", "stderr": str(e), "return_code": -1, "timed_out": False}


def run_kali_command(command: str, timeout: int = 120) -> dict:
    """
    Execute an arbitrary shell command on the Kali Linux server.

    Args:
        command: The shell command to execute (e.g. "ls -la /root")
        timeout: Request timeout in seconds (default 120, max 300)

    Returns:
        dict with stdout, stderr, return_code, success, timed_out
    """
    try:
        resp = requests.post(
            f"{KALI_SERVER_URL}/api/command",
            json={"command": command},
            headers=KALI_REQUEST_HEADERS,
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        return {"success": False, "stdout": "", "stderr": str(e), "return_code": -1, "timed_out": False}


if __name__ == "__main__":
    print(f"Kali server: {KALI_SERVER_URL}")
    print(f"Connection: {check_mcp_connection()}")
    tools = list_mcp_tools()
    available = [t["name"] for t in tools if t.get("available")]
    print(f"Available tools ({len(available)}): {', '.join(available)}")
