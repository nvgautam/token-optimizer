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
from urllib.parse import urlparse, parse_qs
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

class KeyServer(HTTPServer):
    def __init__(self, server_address, RequestHandlerClass, token: str, skills_dir: str):
        super().__init__(server_address, RequestHandlerClass)
        self.token = token
        self.skills_dir = skills_dir
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
        path = parsed_url.path
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
        self.server.clean_expired_keys()
        key_bytes = generate_ephemeral_key()
        key_id = str(uuid.uuid4())
        
        # Ephemeral key expires in 5 minutes (300 seconds)
        expiry = time.time() + 300
        with self.server.lock:
            self.server.active_keys[key_id] = (key_bytes, expiry)

        response_data = {
            "key_id": key_id,
            "key": key_bytes.hex()
        }
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response_data).encode("utf-8"))

    def handle_skill_serving(self, skill_name: str, key_id: str | None):
        if not key_id:
            self.send_error_response(400, "Missing key ID")
            return

        self.server.clean_expired_keys()

        with self.server.lock:
            if key_id not in self.server.active_keys:
                self.send_error_response(400, "Invalid key ID or key expired")
                return
            key_bytes, _ = self.server.active_keys[key_id]

        skills_dir = Path(self.server.skills_dir)
        skill_file = skills_dir / skill_name / "SKILL.md"
        if not skill_file.is_file():
            skill_file = skills_dir / skill_name
            if not skill_file.is_file():
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


def run_server_in_thread(host: str, port: int, token: str, skills_dir: str):
    server = KeyServer((host, port), KeyServerHandler, token, skills_dir)
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
