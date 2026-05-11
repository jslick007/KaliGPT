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


def _is_500_error(e: Exception) -> bool:
    status = getattr(e, "status_code", None) or getattr(e, "code", None)
    # 500-599 are server errors
    return status is not None and 500 <= status < 600


def _wait_for_error(e: Exception, on_retry=None, is_500=False):
    if is_500:
        wait = 5
    else:
        wait = None
        resp = getattr(e, "response", None)
        if resp is not None:
            headers = getattr(resp, "headers", resp)
            if not isinstance(headers, dict):
                try:
                    headers = dict(headers)
                except (TypeError, ValueError):
                    headers = {}
            wait = _parse_retry_after(headers)
        
        if wait is None:
            if resp is not None and hasattr(resp, "json"):
                try:
                    wait = _extract_delay_from_json(resp.json())
                except Exception:
                    pass
            if wait is None:
                json_data = getattr(e, "response_json", None)
                if json_data:
                    wait = _extract_delay_from_json(json_data)
        
        if wait is None:
            wait = 15
            
    print(f"\n[!] Server error ({getattr(e, 'status_code', getattr(e, 'code', 'Unknown'))}). Retrying in {wait}s...")
    
    if on_retry:
        on_retry()
        
    time.sleep(wait)


def retry_on_429(fn, on_retry=None):
    """Call fn(), retrying on 429 (indefinitely) and 500 (up to 3x) errors.
    
    If 500 errors exceed 3 attempts, it triggers on_retry to cycle the model.
    """
    count_500 = 0
    while True:
        try:
            return fn()
        except Exception as e:
            if _is_429_error(e):
                _wait_for_error(e, on_retry=on_retry, is_500=False)
                continue
            
            if _is_500_error(e):
                count_500 += 1
                if count_500 <= 3:
                    print(f"\n[!] Server error 500 (Attempt {count_500}/3). Retrying in 5s...")
                    time.sleep(5)
                    continue
                else:
                    print("\n[!] Server error 500 persisted after 3 attempts. Cycling model...")
                    _wait_for_error(e, on_retry=on_retry, is_500=False) # Trigger model cycle
                    count_500 = 0
                    continue
            
            raise e


def retry_stream(factory, on_retry=None):
    """Generator that yields from factory(), retrying on 429/500 errors.
    
    If 500 errors exceed 3 attempts, it triggers on_retry to cycle the model.
    """
    count_500 = 0
    while True:
        try:
            yield from factory()
            return
        except Exception as e:
            if _is_429_error(e):
                _wait_for_error(e, on_retry=on_retry, is_500=False)
                continue
            
            if _is_500_error(e):
                count_500 += 1
                if count_500 <= 3:
                    print(f"\n[!] Server error 500 (Attempt {count_500}/3). Retrying in 5s...")
                    time.sleep(5)
                    continue
                else:
                    print("\n[!] Server error 500 persisted after 3 attempts. Cycling model...")
                    _wait_for_error(e, on_retry=on_retry, is_500=False) # Trigger model cycle
                    count_500 = 0
                    continue
            
            raise e



