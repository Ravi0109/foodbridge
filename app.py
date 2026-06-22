#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import mimetypes
import json
import os
import re
import secrets
import time
import traceback
import urllib.parse
import uuid
from datetime import datetime, timezone
from functools import partial
from http import cookies
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage"
UPLOAD_DIR = STORAGE_DIR / "uploads"
CONTACT_LOG = STORAGE_DIR / "contact_messages.jsonl"
DONATION_LOG = STORAGE_DIR / "donation_submissions.jsonl"
RECIPIENT_LOG = STORAGE_DIR / "recipient_registrations.jsonl"
VOLUNTEER_LOG = STORAGE_DIR / "volunteer_signups.jsonl"
PARTNERSHIP_LOG = STORAGE_DIR / "partnership_inquiries.jsonl"
QUICK_REQUEST_LOG = STORAGE_DIR / "quick_requests.jsonl"
ADMIN_CREDENTIALS_FILE = STORAGE_DIR / "admin_credentials.json"
ADMIN_SECRET_FILE = STORAGE_DIR / "admin_secret.key"
ADMIN_COOKIE_NAME = "foodbridge_admin"
ADMIN_SESSION_TTL_SECONDS = 8 * 60 * 60
DEFAULT_ADMIN_USERNAME = os.environ.get("FOODBRIDGE_ADMIN_USER", "admin")
DEFAULT_ADMIN_PASSWORD = os.environ.get("FOODBRIDGE_ADMIN_PASSWORD", "FoodBridge@123")

ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_DOC_EXTS = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}
PHOTO_MAX_BYTES = 5 * 1024 * 1024
DOC_MAX_BYTES = 10 * 1024 * 1024


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_runtime_dirs() -> None:
    STORAGE_DIR.mkdir(exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

def init_storage() -> None:
    ensure_runtime_dirs()
    for path in [
        CONTACT_LOG,
        DONATION_LOG,
        RECIPIENT_LOG,
        VOLUNTEER_LOG,
        PARTNERSHIP_LOG,
        QUICK_REQUEST_LOG,
    ]:
        path.touch(exist_ok=True)
    ensure_admin_credentials()
    ensure_admin_secret()


def ensure_admin_credentials() -> None:
    if ADMIN_CREDENTIALS_FILE.exists():
        return

    salt = secrets.token_hex(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        DEFAULT_ADMIN_PASSWORD.encode("utf-8"),
        salt.encode("utf-8"),
        200_000,
    ).hex()
    payload = {
        "username": DEFAULT_ADMIN_USERNAME,
        "salt": salt,
        "iterations": 200_000,
        "password_hash": password_hash,
    }
    ADMIN_CREDENTIALS_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def ensure_admin_secret() -> None:
    if ADMIN_SECRET_FILE.exists():
        return

    ADMIN_SECRET_FILE.write_text(secrets.token_urlsafe(48), encoding="utf-8")


def load_admin_credentials() -> dict:
    ensure_admin_credentials()
    return json.loads(ADMIN_CREDENTIALS_FILE.read_text(encoding="utf-8"))


def load_admin_secret() -> str:
    ensure_admin_secret()
    return ADMIN_SECRET_FILE.read_text(encoding="utf-8").strip()


def verify_admin_password(username: str, password: str) -> bool:
    credentials = load_admin_credentials()
    if normalize_username(username) != normalize_username(credentials.get("username")):
        return False

    salt = clean_str(credentials.get("salt"))
    iterations = int(credentials.get("iterations") or 200_000)
    expected_hash = clean_str(credentials.get("password_hash"))
    actual_hash = hashlib.pbkdf2_hmac(
        "sha256",
        clean_str(password).encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    ).hex()
    return hmac.compare_digest(actual_hash, expected_hash)


def build_admin_cookie_value(username: str) -> str:
    expiry = str(int(time.time()) + ADMIN_SESSION_TTL_SECONDS)
    nonce = secrets.token_urlsafe(12)
    payload = f"{username}:{expiry}:{nonce}"
    signature = hmac.new(
        load_admin_secret().encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    token = f"{payload}:{signature}".encode("utf-8")
    return base64.urlsafe_b64encode(token).decode("ascii")


def parse_admin_cookie_value(token: str) -> dict | None:
    if not token:
        return None

    try:
        decoded = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        username, expiry_text, nonce, signature = decoded.split(":", 3)
        expiry = int(expiry_text)
    except Exception:
        return None

    if expiry < int(time.time()):
        return None

    payload = f"{username}:{expiry}:{nonce}"
    expected_signature = hmac.new(
        load_admin_secret().encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        return None

    credentials = load_admin_credentials()
    if normalize_username(username) != normalize_username(credentials.get("username")):
        return None

    return {
        "username": username,
        "expiry": expiry,
        "nonce": nonce,
    }


def get_cookie_value(handler, cookie_name: str) -> str:
    raw_cookie = handler.headers.get("Cookie")
    if not raw_cookie:
        return ""

    jar = cookies.SimpleCookie()
    try:
        jar.load(raw_cookie)
    except cookies.CookieError:
        return ""

    morsel = jar.get(cookie_name)
    return morsel.value if morsel else ""


def is_admin_authenticated(handler) -> bool:
    return parse_admin_cookie_value(get_cookie_value(handler, ADMIN_COOKIE_NAME)) is not None


def build_cookie_header(name: str, value: str, *, max_age: int | None = None) -> str:
    parts = [f"{name}={value}", "Path=/", "HttpOnly", "SameSite=Lax"]
    if max_age is not None:
        parts.append(f"Max-Age={max_age}")
    return "; ".join(parts)


def build_clear_cookie_header(name: str) -> str:
    return f"{name}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"


def clean_str(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", "ignore")
    return str(value).strip()


def normalize_username(value) -> str:
    return clean_str(value).casefold()


def parse_bool(value) -> int:
    return 1 if clean_str(value).lower() in {"1", "true", "yes", "on"} else 0


def parse_int(value, field_name: str) -> int:
    value = clean_str(value)
    if not value:
        raise ValueError(f"{field_name} is required.")
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a number.") from exc


def upload_filename(field) -> str:
    if field is None:
        return ""
    if hasattr(field, "filename"):
        return getattr(field, "filename") or ""
    if isinstance(field, dict):
        return field.get("filename") or ""
    return ""


def upload_content(field) -> bytes:
    if field is None:
        return b""
    if hasattr(field, "file"):
        return field.file.read()
    if isinstance(field, dict):
        content = field.get("content")
        if isinstance(content, bytes):
            return content
        if content is None:
            return b""
        return str(content).encode("utf-8")
    if isinstance(field, bytes):
        return field
    return clean_str(field).encode("utf-8")


def save_upload(field, subdir: str, allowed_exts, max_bytes: int):
    filename = upload_filename(field)
    if not filename:
        return None

    original_name = Path(filename).name
    suffix = Path(original_name).suffix.lower()
    if suffix not in allowed_exts:
        raise ValueError(f"Unsupported file type for {original_name}.")

    content = upload_content(field)
    if len(content) > max_bytes:
        raise ValueError(f"{original_name} exceeds the allowed file size.")

    target_dir = UPLOAD_DIR / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{suffix}"
    stored_path = target_dir / stored_name
    stored_path.write_bytes(content)
    return str(stored_path.relative_to(BASE_DIR))


def parse_multipart(body: bytes, content_type: str):
    match = re.search(r'boundary=(?:"?)([^";]+)', content_type)
    if not match:
        raise ValueError("Missing multipart boundary.")

    boundary = match.group(1).encode("utf-8")
    delimiter = b"--" + boundary
    data = {}
    files = {}

    for part in body.split(delimiter):
        part = part.lstrip(b"\r\n")
        if not part or part == b"--":
            continue
        if part.endswith(b"--"):
            part = part[:-2]
        header_blob, separator, content = part.partition(b"\r\n\r\n")
        if not separator:
            continue

        header_lines = header_blob.decode("utf-8", "replace").split("\r\n")
        headers = {}
        for line in header_lines:
            if ":" not in line:
                continue
            name, value = line.split(":", 1)
            headers[name.strip().lower()] = value.strip()

        disposition = headers.get("content-disposition", "")
        name_match = re.search(r'name="([^"]+)"', disposition)
        if not name_match:
            continue

        field_name = name_match.group(1)
        filename_match = re.search(r'filename="([^"]*)"', disposition)
        content = content.rstrip(b"\r\n")

        if filename_match and filename_match.group(1):
            files[field_name] = {
                "filename": filename_match.group(1),
                "content": content,
                "content_type": headers.get("content-type", "application/octet-stream"),
            }
        else:
            data[field_name] = content.decode("utf-8", "replace")

    return data, files


def parse_post_body(handler):
    content_type = handler.headers.get("Content-Type", "")
    length = int(handler.headers.get("Content-Length", "0") or "0")
    body = handler.rfile.read(length) if length else b""

    if "application/json" in content_type:
        if not body:
            return {}, {}
        return json.loads(body.decode("utf-8")), {}

    if "multipart/form-data" in content_type:
        return parse_multipart(body, content_type)

    parsed = urllib.parse.parse_qs(body.decode("utf-8", "ignore"), keep_blank_values=True)
    return {key: values[-1] for key, values in parsed.items()}, {}


def wants_json(handler) -> bool:
    accept = handler.headers.get("Accept", "")
    xhr = handler.headers.get("X-Requested-With", "")
    return "application/json" in accept or xhr.lower() == "xmlhttprequest"


def send_json(handler, status: int, payload, headers: dict[str, str] | None = None) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    if headers:
        for key, value in headers.items():
            handler.send_header(key, value)
    handler.end_headers()
    handler.wfile.write(body)


def redirect(handler, location: str, headers: dict[str, str] | None = None, status: int = 303) -> None:
    handler.send_response(status)
    handler.send_header("Location", location)
    if headers:
        for key, value in headers.items():
            handler.send_header(key, value)
    handler.end_headers()


def submission_response(handler, payload, redirect_to: str) -> None:
    if wants_json(handler):
        send_json(handler, 200, {"success": True, **payload})
    else:
        redirect(handler, redirect_to)


def new_record_id() -> str:
    return uuid.uuid4().hex[:12]


def append_record(path: Path, record: dict) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False))
        handle.write("\n")


def read_jsonl_records(path: Path) -> list[dict]:
    records = []
    if not path.exists():
        return records

    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                records.append(record)

    records.sort(key=lambda item: clean_str(item.get("created_at")), reverse=True)
    return records


def make_admin_file_url(raw_path: str) -> str:
    normalized = clean_str(raw_path).replace("\\", "/")
    if not normalized:
        return ""
    return "/api/admin/file?path=" + urllib.parse.quote(normalized, safe="/")


def with_attachments(record: dict, fields: list[tuple[str, str]]) -> dict:
    enriched = dict(record)
    attachments = []
    for label, field_name in fields:
        raw_path = clean_str(record.get(field_name))
        if not raw_path:
            continue
        attachments.append(
            {
                "label": label,
                "name": Path(raw_path.replace("\\", "/")).name,
                "path": raw_path,
                "url": make_admin_file_url(raw_path),
            }
        )
    enriched["attachments"] = attachments
    return enriched


def build_admin_payload() -> dict:
    contacts = read_jsonl_records(CONTACT_LOG)
    donations = [with_attachments(item, [("Food photo", "photo_path")]) for item in read_jsonl_records(DONATION_LOG)]
    requests = [
        with_attachments(item, [("Registration certificate", "registration_path"), ("Proof of work", "proof_path")])
        for item in read_jsonl_records(RECIPIENT_LOG)
    ]
    volunteers = read_jsonl_records(VOLUNTEER_LOG)
    partnerships = read_jsonl_records(PARTNERSHIP_LOG)
    quick_requests = read_jsonl_records(QUICK_REQUEST_LOG)

    return {
        "success": True,
        "generated_at": utc_now(),
        "summary": {
            "contact_messages": len(contacts),
            "donations": len(donations),
            "requests": len(requests),
            "volunteers": len(volunteers),
            "partnerships": len(partnerships),
            "quick_requests": len(quick_requests),
            "total": len(contacts) + len(donations) + len(requests) + len(volunteers) + len(partnerships) + len(quick_requests),
        },
        "sections": {
            "contact_messages": contacts,
            "donations": donations,
            "requests": requests,
            "volunteers": volunteers,
            "partnerships": partnerships,
            "quick_requests": quick_requests,
        },
    }


def serve_admin_file(handler, query: dict[str, list[str]]) -> bool:
    raw_path = clean_str(query.get("path", [""])[0])
    if not raw_path:
        handler.send_error(400, "Missing file path")
        return True

    normalized = Path(raw_path.replace("\\", "/"))
    resolved = (BASE_DIR / normalized).resolve()
    upload_root = UPLOAD_DIR.resolve()

    if not resolved.is_file() or upload_root not in resolved.parents:
        handler.send_error(404, "Not Found")
        return True

    content = resolved.read_bytes()
    content_type = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(content)))
    handler.send_header("Content-Disposition", f'inline; filename="{resolved.name}"')
    handler.end_headers()
    handler.wfile.write(content)
    return True


def insert_contact(data) -> str:
    record_id = new_record_id()
    append_record(
        CONTACT_LOG,
        {
            "id": record_id,
            "name": clean_str(data.get("name")),
            "email": clean_str(data.get("email")),
            "phone": clean_str(data.get("phone")),
            "subject": clean_str(data.get("subject")),
            "message": clean_str(data.get("message")),
            "created_at": utc_now(),
        },
    )
    return record_id


def insert_donation(data, files) -> str:
    recurring = parse_bool(data.get("recurring"))
    photo_path = save_upload(files.get("foodPhoto"), "donations", ALLOWED_IMAGE_EXTS, PHOTO_MAX_BYTES)
    record_id = new_record_id()
    append_record(
        DONATION_LOG,
        {
            "id": record_id,
            "name": clean_str(data.get("name")),
            "email": clean_str(data.get("email")),
            "phone": clean_str(data.get("phone")),
            "address": clean_str(data.get("address")),
            "food_type": clean_str(data.get("foodType")),
            "quantity": clean_str(data.get("quantity")),
            "description": clean_str(data.get("description")),
            "expiry_date": clean_str(data.get("expiryDate")),
            "pickup_time": clean_str(data.get("pickupTime")),
            "pickup_method": clean_str(data.get("pickupMethod")),
            "recurring": recurring,
            "frequency": clean_str(data.get("frequency")) if recurring else "",
            "photo_path": photo_path,
            "created_at": utc_now(),
        },
    )
    return record_id


def insert_recipient(data, files) -> str:
    beneficiaries = parse_int(data.get("beneficiaries"), "Estimated Beneficiaries")
    registration_path = save_upload(
        files.get("registration"), "registrations", ALLOWED_DOC_EXTS, DOC_MAX_BYTES
    )
    proof_path = save_upload(files.get("proof"), "proofs", ALLOWED_DOC_EXTS, DOC_MAX_BYTES)

    if not registration_path:
        raise ValueError("Registration certificate is required.")
    if not proof_path:
        raise ValueError("Proof of work is required.")

    record_id = new_record_id()
    append_record(
        RECIPIENT_LOG,
        {
            "id": record_id,
            "org_name": clean_str(data.get("orgName")),
            "org_type": clean_str(data.get("orgType")),
            "reg_number": clean_str(data.get("regNumber")),
            "contact_name": clean_str(data.get("contactName")),
            "contact_email": clean_str(data.get("contactEmail")),
            "contact_phone": clean_str(data.get("contactPhone")),
            "pickup_address": clean_str(data.get("pickupAddress")),
            "beneficiaries": beneficiaries,
            "food_needs": clean_str(data.get("foodNeeds")),
            "description": clean_str(data.get("description")),
            "registration_path": registration_path,
            "proof_path": proof_path,
            "created_at": utc_now(),
        },
    )
    return record_id


def insert_volunteer(data) -> str:
    record_id = new_record_id()
    append_record(
        VOLUNTEER_LOG,
        {
            "id": record_id,
            "name": clean_str(data.get("volName")),
            "email": clean_str(data.get("volEmail")),
            "phone": clean_str(data.get("volPhone")),
            "area": clean_str(data.get("volArea")),
            "role": clean_str(data.get("volRole")),
            "availability": clean_str(data.get("volAvailability")),
            "bio": clean_str(data.get("volBio")),
            "created_at": utc_now(),
        },
    )
    return record_id


def insert_partnership(data) -> str:
    record_id = new_record_id()
    append_record(
        PARTNERSHIP_LOG,
        {
            "id": record_id,
            "organization_name": clean_str(data.get("partName")),
            "organization_type": clean_str(data.get("partType")),
            "contact_person": clean_str(data.get("partContact")),
            "email": clean_str(data.get("partEmail")),
            "phone": clean_str(data.get("partPhone")),
            "location": clean_str(data.get("partLocation")),
            "interest": clean_str(data.get("partInterest")),
            "created_at": utc_now(),
        },
    )
    return record_id


def insert_quick_request(data) -> str:
    record_id = new_record_id()
    append_record(
        QUICK_REQUEST_LOG,
        {
            "id": record_id,
            "title": clean_str(data.get("title")),
            "donor": clean_str(data.get("donor")),
            "location": clean_str(data.get("location")),
            "food_type": clean_str(data.get("food_type")),
            "available_date": clean_str(data.get("available_date")),
            "summary": clean_str(data.get("summary")),
            "created_at": utc_now(),
        },
    )
    return record_id


class FoodBridgeHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)

        if path in {"/admin", "/admin/", "/admin.html"}:
            if not is_admin_authenticated(self):
                redirect(self, "/admin-login")
                return
            self.path = "/admin.html"
            return super().do_GET()

        if path in {"/admin-login", "/admin-login/", "/admin-login.html"}:
            if is_admin_authenticated(self):
                redirect(self, "/admin")
                return
            self.path = "/admin-login.html"
            return super().do_GET()

        if path in {"/admin-logout", "/admin-logout/"}:
            redirect(
                self,
                "/admin-login?logged_out=1",
                headers={"Set-Cookie": build_clear_cookie_header(ADMIN_COOKIE_NAME)},
            )
            return

        if path.startswith("/api/"):
            if path == "/api/health":
                send_json(self, 200, {"success": True, "status": "ok"})
            elif path == "/api/admin/data":
                if not is_admin_authenticated(self):
                    send_json(self, 401, {"success": False, "error": "Unauthorized"})
                    return
                send_json(self, 200, build_admin_payload())
            elif path == "/api/admin/file":
                if not is_admin_authenticated(self):
                    redirect(self, "/admin-login")
                    return
                serve_admin_file(self, query)
            else:
                self.send_error(405, "Method Not Allowed")
            return

        if path.startswith("/storage/"):
            self.send_error(404, "Not Found")
            return

        super().do_GET()

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path

        try:
            data, files = parse_post_body(self)

            if path == "/api/admin/login":
                username = clean_str(data.get("username"))
                password = clean_str(data.get("password"))
                if verify_admin_password(username, password):
                    cookie_value = build_admin_cookie_value(username)
                    headers = {"Set-Cookie": build_cookie_header(ADMIN_COOKIE_NAME, cookie_value, max_age=ADMIN_SESSION_TTL_SECONDS)}
                    if wants_json(self):
                        send_json(
                            self,
                            200,
                            {"success": True, "message": "Logged in successfully."},
                            headers=headers,
                        )
                    else:
                        redirect(self, "/admin", headers=headers)
                    return

                if wants_json(self):
                    send_json(self, 401, {"success": False, "error": "Invalid username or password."})
                else:
                    redirect(self, "/admin-login?error=1")
                return

            if path == "/api/contact":
                submission_id = insert_contact(data)
                submission_response(
                    self,
                    {
                        "message": "Thank you for your message! We will get back to you within 24 hours.",
                        "id": submission_id,
                    },
                    "/contact.html",
                )
                return

            if path == "/api/donations":
                submission_id = insert_donation(data, files)
                submission_response(
                    self,
                    {
                        "message": "Thank you for your donation! Your food donation has been submitted. Our team will contact you shortly for pickup coordination.",
                        "id": submission_id,
                    },
                    "/donate.html",
                )
                return

            if path == "/api/requests":
                submission_id = insert_recipient(data, files)
                submission_response(
                    self,
                    {
                        "message": "Thank you for registering! Your organization will be verified within 24 hours. You will receive a confirmation email shortly.",
                        "id": submission_id,
                    },
                    "/request.html",
                )
                return

            if path == "/api/volunteers":
                submission_id = insert_volunteer(data)
                submission_response(
                    self,
                    {
                        "message": "Thank you for signing up! We will contact you soon with more details.",
                        "id": submission_id,
                    },
                    "/partner.html#volunteer-form",
                )
                return

            if path == "/api/partnerships":
                submission_id = insert_partnership(data)
                submission_response(
                    self,
                    {
                        "message": "Thank you for your interest! Our team will review your inquiry and contact you shortly.",
                        "id": submission_id,
                    },
                    "/partner.html#partner-form",
                )
                return

            if path == "/api/quick-requests":
                submission_id = insert_quick_request(data)
                submission_response(
                    self,
                    {
                        "message": "Request recorded! Our team will review the available donation and respond shortly.",
                        "id": submission_id,
                    },
                    "/request.html",
                )
                return

            self.send_error(404, "Unknown API route")
        except ValueError as error:
            if wants_json(self):
                send_json(self, 400, {"success": False, "error": str(error)})
            else:
                self.send_error(400, str(error))
        except Exception:
            traceback.print_exc()
            if wants_json(self):
                send_json(self, 500, {"success": False, "error": "Server error"})
            else:
                self.send_error(500, "Server error")


def main():
    parser = argparse.ArgumentParser(description="FoodBridge Python server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    init_storage()
    handler = partial(FoodBridgeHandler, directory=str(BASE_DIR))
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"FoodBridge server running at http://{args.host}:{args.port}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
