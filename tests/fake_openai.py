"""A fake OpenAI-compatible server on 127.0.0.1, for the tests and for trying the commands without a model.

    python -m tests.fake_openai [--port 8080] [--delay SECONDS]

It answers POST .../chat/completions and .../completions. A translation request gets the source text
back unchanged (the text after the prompt's first blank line), so scores are those of a system that
copies its input; for a model whose name contains "upper" it comes back in upper case. A judge
request (the release's error or pairwise instruction) gets a valid answer for every key. Tests can
queue scripted replies: "400", "500", "429", "404" (each with an error body that holds BODY_MARKER),
"redirect" (307 to `redirect_to`), "timeout", "empty", "length", "garbage" or "drop" (close the
connection).
"""

import argparse
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

JUDGE = "You are an expert bilingual reviewer"
BODY_MARKER = "internal-detail-db7"  # in every scripted error body; must never be kept by a client


def answer(body):
    """(content, finish_reason) for a request body."""
    if "messages" in body:
        text = body["messages"][-1]["content"]
    else:
        text = body.get("prompt", "")
    if text.startswith(JUDGE):
        payload = json.loads(text[text.index("\n\n{") + 2:])
        if "mapping every key to {\"critical\"" in text:
            reply = {k: dict(critical=0, major=len(v["candidate"]) % 2, minor=len(v["candidate"]) % 3)
                     for k, v in payload.items()}
        else:
            reply = {k: dict(winner="A" if len(v["A"]) >= len(v["B"]) else "B", major_A=0, major_B=1)
                     for k, v in payload.items()}
        return "Here is the result:\n" + json.dumps(reply), "stop"
    if "<start_of_turn>user" in text:
        source = text.split("\n\n\n", 1)[1].split("<end_of_turn>", 1)[0]
    else:
        source = text.split("\n\n", 1)[1] if "\n\n" in text else text
        source = re.sub(r"^#guidelines\n#src_text\n", "", source)
    return (source.upper() if "upper" in str(body.get("model")) else source), "stop"


class Server:
    def __init__(self, port=0, delay=0.0):
        self.script = []  # replies to use before the default behaviour, one per request
        self.requests = []  # (path, headers, body) received
        self.delay = delay
        self.redirect_to = None
        self.lock = threading.Lock()
        handler = self._handler()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
        self.httpd.daemon_threads = True
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def base_url(self):
        return f"http://127.0.0.1:{self.httpd.server_address[1]}/v1"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()

    def _handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                body = json.loads(raw)
                with server.lock:
                    server.requests.append((self.path, dict(self.headers), body))
                    action = server.script.pop(0) if server.script else None
                if server.delay:
                    time.sleep(server.delay)
                if action in ("400", "500", "429", "404"):
                    self.send_json(int(action), dict(error=dict(message=f"scripted {action} at {BODY_MARKER}")))
                    return
                if action == "redirect":
                    self.send_response(307)
                    self.send_header("Location", server.redirect_to)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                if action == "timeout":
                    time.sleep(3)
                if action == "drop":
                    self.close_connection = True
                    self.connection.close()
                    return
                if action == "garbage":
                    self.send_raw(200, b"<html>not json</html>")
                    return
                content, finish = answer(body)
                if action == "empty":
                    content = "   "
                if action == "length":
                    finish = "length"
                choice = dict(index=0, finish_reason=finish)
                if self.path.endswith("/chat/completions"):
                    choice["message"] = dict(role="assistant", content=content)
                else:
                    choice["text"] = content
                self.send_json(200, dict(id="fake", object="chat.completion", model=body.get("model"),
                                         choices=[choice],
                                         usage=dict(prompt_tokens=len(str(body).split()),
                                                    completion_tokens=len(content.split()))))

            def send_json(self, code, value):
                self.send_raw(code, json.dumps(value).encode())

            def send_raw(self, code, data):
                try:
                    self.send_response(code)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        return Handler


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--delay", type=float, default=0.0, help="seconds before each reply")
    args = parser.parse_args(argv)
    server = Server(args.port, args.delay)
    print(f"Fake OpenAI-compatible server at {server.base_url} (Ctrl-C to stop)", flush=True)
    try:
        server.httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.httpd.server_close()


if __name__ == "__main__":
    main()
