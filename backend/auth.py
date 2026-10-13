"""Token ký HMAC cho đăng nhập demo.

Không phải hệ thống xác thực production: danh tính vẫn là danh sách nhân sự demo,
nhưng mọi truy cập dữ liệu (đặc biệt chứng từ y tế) phải mang token ký còn hạn,
không thể tự khai bằng header/query như trước.
"""
import base64
import hashlib
import hmac
import os
import secrets
import time



def _load_secret() -> bytes:
    """Khóa ký token phải giữ nguyên qua các lần khởi động lại (--reload), nếu không mọi token trình duyệt
    đang giữ đều thành 401 và giao diện ngừng cập nhật cho tới khi tải lại trang. Lưu khóa vào thư mục dữ liệu."""
    env_secret = os.getenv("LEAVE_AUTH_SECRET")
    if env_secret:
        return env_secret.encode()
    data_dir = os.getenv("LEAVE_DATA_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    path = os.path.join(data_dir, ".auth_secret")
    try:
        with open(path, "r", encoding="utf-8") as f:
            value = f.read().strip()
        if value:
            return value.encode()
    except OSError:
        pass
    value = secrets.token_hex(32)
    try:
        os.makedirs(data_dir, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(value)
    except OSError:
        pass  # không ghi được: vẫn chạy với khóa trong bộ nhớ như trước
    return value.encode()


_SECRET = _load_secret()
TOKEN_TTL_SECONDS = int(os.getenv("LEAVE_TOKEN_TTL", "28800"))


def _sign(payload: bytes) -> str:
    return hmac.new(_SECRET, payload, hashlib.sha256).hexdigest()


def issue_token(actor_id: str) -> str:
    payload = f"{actor_id}|{int(time.time()) + TOKEN_TTL_SECONDS}".encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=") + "." + _sign(payload)


def verify_token(token: str | None) -> str | None:
    """Trả về actor_id nếu token hợp lệ và chưa hết hạn, ngược lại None."""
    if not token or "." not in token:
        return None
    body, sig = token.rsplit(".", 1)
    try:
        payload = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
    except Exception:
        return None
    if not hmac.compare_digest(sig, _sign(payload)):
        return None
    try:
        actor_id, expires = payload.decode().rsplit("|", 1)
        if int(expires) < time.time():
            return None
    except ValueError:
        return None
    return actor_id


def legacy_actor_header_allowed() -> bool:
    """Header X-Actor-ID tự khai chỉ được phép khi bật rõ ràng (test/dev cục bộ)."""
    return os.getenv("LEAVE_ALLOW_ACTOR_HEADER", "").strip().lower() in {"1", "true", "yes"}


def demo_login_enabled() -> bool:
    return os.getenv("LEAVE_DEMO_LOGIN", "1").strip().lower() not in {"0", "false", "no"}
