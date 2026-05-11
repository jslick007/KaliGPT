import time


def _parse_retry_after(headers: dict) -> float:
    ra = (
        headers.get("retry-after-ms")
        or headers.get("Retry-After")
        or headers.get("retry-after")
    )
    if ra is None:
        return None
    try:
        if "retry-after-ms" in headers:
            return float(ra) / 1000
        return float(ra)
    except ValueError:
        return None


def _extract_delay_from_json(json_data):
    if not isinstance(json_data, dict):
        return None
    error_obj = json_data.get("error", json_data)
    if isinstance(error_obj, dict):
        details = error_obj.get("details", [])
        if isinstance(details, list):
            for detail in details:
                if isinstance(detail, dict) and detail.get("@type") == "type.googleapis.com/google.rpc.RetryInfo":
                    delay_str = detail.get("retryDelay")
                    if delay_str:
                        try:
                            return float(delay_str.rstrip("s"))
                        except ValueError:
                            pass
    return None


def _is_429_error(e: Exception) -> bool:
    status = getattr(e, "status_code", None) or getattr(e, "code", None)
    return status == 429


def _wait_for_429(e: Exception):
    wait = None
    
    # 1. Try headers
    resp = getattr(e, "response", None)
    if resp is not None:
        headers = getattr(resp, "headers", resp)
        if not isinstance(headers, dict):
            try:
                headers = dict(headers)
            except (TypeError, ValueError):
                headers = {}
        wait = _parse_retry_after(headers)
    
    # 2. Try response JSON body
    if wait is None:
        # Case A: e.response is a google-genai Response object or similar with a .json() method
        if resp is not None and hasattr(resp, "json"):
            try:
                wait = _extract_delay_from_json(resp.json())
            except Exception:
                pass
        
        # Case B: Try to find a response_json attribute (fallback)
        if wait is None:
            json_data = getattr(e, "response_json", None)
            if json_data:
                wait = _extract_delay_from_json(json_data)
    
    # 3. Fallback
    if wait is None:
        wait = 15
        
    print(f"\n[!] Rate limited (429). Retrying in {wait}s...")
    time.sleep(wait)



def retry_on_429(fn):
    """Call fn(), retrying on 429 rate-limit errors indefinitely with Retry-After backoff.

    Handles:
      - openai.RateLimitError  (.status_code, .response.headers)
      - google.genai.errors.ClientError (.code, .response.headers)
      - ollama.ResponseError   (.status_code)

    NOTE: if fn() returns a generator/stream, the 429 may be raised lazily
    during iteration rather than inside fn().  For streams use retry_stream()
    instead.
    """
    while True:
        try:
            return fn()
        except Exception as e:
            if not _is_429_error(e):
                raise
            _wait_for_429(e)


def retry_stream(factory):
    """Generator that yields from factory(), retrying the entire stream on 429 indefinitely.

    Unlike retry_on_429(), this handles the case where the SDK returns a lazy
    generator and the 429 error is raised during iteration rather than during
    the initial call to ``factory()`` (e.g. google-genai's
    generate_content_stream).

    Usage::

        for chunk in retry_stream(lambda: client.models.generate_content_stream(...)):
            ...
    """
    while True:
        try:
            yield from factory()
            return
        except Exception as e:
            if not _is_429_error(e):
                raise
            _wait_for_429(e)
