import json
import os
import sys
import time
import urllib.request
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", stream=sys.stderr)
logger = logging.getLogger(__name__)
def main() -> None:
    if sys.prefix == sys.base_prefix:
        sys.stderr.write("Esegui questo script dentro una virtualenv (.venv)\n")
        sys.stderr.write("Esempio: source mc-automesh/.venv/bin/activate\n")
        sys.exit(2)

    router_url = os.environ.get("ROUTER_URL", "http://localhost:7010").rstrip("/")
    logger.info("Router URL: %s", router_url)
    function_name = "math.add"
    logger.info("Function: %s", function_name)
    roles_raw = os.environ.get("ROLES", "")
    tenant = os.environ.get("TENANT", None)
    
    repeat_raw = os.environ.get("REPEAT", "1")
    sleep_s_raw = os.environ.get("SLEEP_S", "0")
    
    try:
        arguments = json.loads("{}")

    except Exception:
        sys.stderr.write("ARGUMENTS_JSON must be valid JSON\n")
        sys.exit(2)

    roles = [r.strip() for r in roles_raw.split(",") if r.strip()] if roles_raw else []

    payload = {
        "function": function_name,
        "arguments": arguments,
        "context": {
            "roles": roles,
            "tenant": tenant,
        },
    }

    try:
        repeat = int(repeat_raw)
    except Exception:
        sys.stderr.write("REPEAT must be an integer\n")
        sys.exit(2)

    try:
        sleep_s = float(sleep_s_raw)
    except Exception:
        sys.stderr.write("SLEEP_S must be a number\n")
        sys.exit(2)

    for i in range(max(1, repeat)):
        req = urllib.request.Request(
            f"{router_url}/call",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = resp.read().decode("utf-8")
                sys.stdout.write(body)
                sys.stdout.write("\n")
        except Exception as e:
            sys.stderr.write(f"Call failed: {str(e)}\n")
            sys.exit(1)

        if sleep_s > 0 and i < (max(1, repeat) - 1):
            time.sleep(sleep_s)


if __name__ == "__main__":
    main()
