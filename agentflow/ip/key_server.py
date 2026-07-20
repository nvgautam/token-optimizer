import os
import sys
import json
import time
import uuid
import secrets
import threading
import argparse
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs, unquote
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

class KeyServer(HTTPServer):
    def __init__(
        self,
        server_address,
        RequestHandlerClass,
        token: str,
        skills_dir: str,
        master_key: bytes | None = None,
    ):
        super().__init__(server_address, RequestHandlerClass)
        self.token = token
        self.skills_dir = skills_dir
        self.master_key = master_key  # If set, /key serves this key (license-revocation mode)
        self.active_keys = {}  # key_id -> (key_bytes, expiry_time)
        self.lock = threading.Lock()

    def clean_expired_keys(self):
        with self.lock:
            now = time.time()
            expired = [k for k, (_, exp) in self.active_keys.items() if now > exp]
            for k in expired:
                del self.active_keys[k]

    def authenticate(self, headers) -> bool:
        auth_header = headers.get("Authorization")
        if not auth_header:
            return False
        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return False
        return secrets.compare_digest(parts[1], self.token)


class KeyServerHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress request log print statements to avoid polluting output
        pass

    def send_error_response(self, status_code: int, message: str):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"error": message}).encode("utf-8"))

    def do_GET(self):
        if not self.server.authenticate(self.headers):
            self.send_error_response(401, "Unauthorized")
            return

        parsed_url = urlparse(self.path)
        path = unquote(parsed_url.path)
        query = parse_qs(parsed_url.query)

        if path == "/key":
            self.handle_key_issuance()
        elif path.startswith("/skill/"):
            skill_name = path[len("/skill/"):]
            key_id = None
            if "key_id" in query:
                key_id = query["key_id"][0]
            elif "X-Key-ID" in self.headers:
                key_id = self.headers["X-Key-ID"]
            self.handle_skill_serving(skill_name, key_id)
        else:
            self.send_error_response(404, "Not Found")

    def handle_key_issuance(self):
        if self.server.master_key is not None:
            # Master-key mode: serve the pre-shared encryption key; no key_id
            response_data = {"key": self.server.master_key.hex()}
        else:
            # Ephemeral-key mode (default): generate a fresh short-lived key
            self.server.clean_expired_keys()
            key_bytes = generate_ephemeral_key()
            key_id = str(uuid.uuid4())
            expiry = time.time() + 300
            with self.server.lock:
                self.server.active_keys[key_id] = (key_bytes, expiry)
            response_data = {"key_id": key_id, "key": key_bytes.hex()}
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response_data).encode("utf-8"))

    def handle_skill_serving(self, skill_name: str, key_id: str | None):
        if not key_id:
            self.send_error_response(400, "Missing key ID")
            return

        self.server.clean_expired_keys()

        key_bytes = None
        with self.server.lock:
            if key_id in self.server.active_keys:
                key_bytes, _ = self.server.active_keys[key_id]

        if not key_bytes:
            self.send_error_response(400, "Invalid key ID or key expired")
            return

        skills_dir = Path(self.server.skills_dir).resolve()
        candidate_1 = (skills_dir / skill_name / "SKILL.md").resolve()
        candidate_2 = (skills_dir / skill_name).resolve()

        try:
            candidate_1.relative_to(skills_dir)
            candidate_2.relative_to(skills_dir)
        except ValueError:
            self.send_error_response(400, "Invalid skill path")
            return

        skill_file = None
        if candidate_1.is_file():
            skill_file = candidate_1
        elif candidate_2.is_file():
            skill_file = candidate_2

        if not skill_file:
            self.send_error_response(404, "Skill not found")
            return

        try:
            content = skill_file.read_bytes()
        except Exception as e:
            self.send_error_response(500, f"Error reading skill: {str(e)}")
            return

        try:
            aesgcm = AESGCM(key_bytes)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, content, None)

            response_data = {
                "nonce": nonce.hex(),
                "ciphertext": ciphertext.hex()
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode("utf-8"))
        except Exception as e:
            self.send_error_response(500, f"Encryption failed: {str(e)}")


def generate_ephemeral_key() -> bytes:
    return AESGCM.generate_key(bit_length=256)


def run_server_in_thread(
    host: str,
    port: int,
    token: str,
    skills_dir: str,
    master_key: bytes | None = None,
):
    server = KeyServer((host, port), KeyServerHandler, token, skills_dir, master_key=master_key)
    bound_port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, bound_port


def main() -> None:
    parser = argparse.ArgumentParser(description="Lightweight HTTP Key Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on")
    parser.add_argument("--token", help="Bearer token for authentication (or set KEY_SERVER_TOKEN)")
    parser.add_argument("--skills-dir", default="agentflow/skills", help="Directory where skills are located")
    args = parser.parse_args()

    token = args.token or os.environ.get("KEY_SERVER_TOKEN")
    if not token:
        print("Error: Authentication token must be provided via --token or KEY_SERVER_TOKEN environment variable.", file=sys.stderr)
        sys.exit(1)

    print(f"Starting key server on {args.host}:{args.port}...")
    print(f"Serving skills from: {args.skills_dir}")
    server = KeyServer((args.host, args.port), KeyServerHandler, token, args.skills_dir)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping key server.")
        server.server_close()


if __name__ == "__main__":
    main()
