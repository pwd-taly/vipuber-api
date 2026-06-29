"""VipUber session management with auto-reconnect on expiry."""

import hashlib
import io
import time
import threading
import logging
import urllib.request
import urllib.parse
import urllib.error
import http.cookiejar

from PIL import Image, ImageEnhance
import pytesseract

from config import get_settings

log = logging.getLogger("vipuber.session")


class SessionError(Exception):
    """Raised when a VipUber session operation fails."""


class SessionExpired(Exception):
    """Raised when the session has expired and needs re-login."""


class VipUberSession:
    """Manages a single VipUber session with automatic captcha solving.

    Thread-safe: all state mutations are protected by an instance-level lock.
    """

    MAX_LOGIN_ATTEMPTS = 5

    def __init__(self, email: str, password: str, base_url: str, customer_id: str,
                 timeout: int = 30):
        self.email = email
        self.password = password
        self.base_url = base_url.rstrip("/")
        self.customer_id = customer_id
        self.timeout = timeout
        self.cj = http.cookiejar.CookieJar()
        self.opener = self._build_opener()
        self._logged_in = False
        self._login_time = 0.0
        self._lock = threading.Lock()

    # ── opener ──────────────────────────────────────────

    def _build_opener(self) -> urllib.request.OpenerDirector:
        self.cj = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cj)
        )
        opener.addheaders = [
            (
                "User-Agent",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36",
            ),
            ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
            ("Accept-Language", "tr-TR,tr;q=0.9,en;q=0.8"),
        ]
        return opener

    # ── captcha ─────────────────────────────────────────

    def _solve_captcha(self) -> str:
        """Fetch the captcha image and solve with Tesseract OCR."""
        try:
            resp = self.opener.open(f"{self.base_url}/security.php", timeout=self.timeout)
            img_data = resp.read()
            img = Image.open(io.BytesIO(img_data)).convert("L")
            img = ImageEnhance.Contrast(img).enhance(2.0)
            img = img.point(lambda x: 0 if x < 200 else 255)
            code = pytesseract.image_to_string(
                img,
                config="--oem 3 --psm 7 -c tesseract_char_whitelist=0123456789",
            ).strip()
            return code if code else "000"
        except Exception as exc:
            log.warning("Captcha fetch/solve failed: %s", exc)
            return "000"

    # ── login (internal, callers must hold self._lock) ──

    def _login_locked(self) -> "VipUberSession":
        """Authenticate with email/password + captcha. Retries on failure.

        Caller MUST hold self._lock.
        """
        for attempt in range(self.MAX_LOGIN_ATTEMPTS):
            self.opener = self._build_opener()

            try:
                # Visit login page first to get initial cookies
                self.opener.open(f"{self.base_url}/giris.php", timeout=self.timeout)
            except Exception as exc:
                log.warning("Login page fetch failed (attempt %d): %s", attempt + 1, exc)
                continue

            # Solve captcha
            captcha = self._solve_captcha()
            data = urllib.parse.urlencode({
                "kadi": self.email,
                "sifre": self.password,
                "security": captcha,
                "git": f"{self.base_url}/",
            }).encode("iso-8859-9")

            try:
                resp = self.opener.open(
                    f"{self.base_url}/giris/giris_kontrol.php", data, timeout=self.timeout
                )
                body = resp.read().decode("iso-8859-9", errors="replace")
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("iso-8859-9", errors="replace")
            except Exception as exc:
                log.warning("Login request failed (attempt %d): %s", attempt + 1, exc)
                continue

            if "yanlis" not in body.lower():
                # Hit homepage to finalize session
                try:
                    self.opener.open(f"{self.base_url}/", timeout=self.timeout)
                except Exception:
                    pass
                self._logged_in = True
                self._login_time = time.time()
                log.info("Logged in as %s (session established)", self.email)
                return self

            log.warning(
                "Login attempt %d/%d failed (bad captcha or credentials)",
                attempt + 1,
                self.MAX_LOGIN_ATTEMPTS,
            )

        raise SessionError(
            f"Login failed after {self.MAX_LOGIN_ATTEMPTS} attempts. "
            "Check credentials and captcha setup."
        )

    def login(self) -> "VipUberSession":
        """Authenticate with email/password + captcha. Retries on failure.

        Thread-safe: holds the instance lock during the entire login sequence.
        """
        with self._lock:
            return self._login_locked()

    # ── ensure logged in ────────────────────────────────

    def _ensure_login_locked(self):
        """Re-login if not authenticated.  Caller MUST hold self._lock."""
        if not self._logged_in:
            self._login_locked()

    def ensure_login(self):
        """Re-login if not authenticated (thread-safe)."""
        with self._lock:
            self._ensure_login_locked()

    # ── HTTP methods ────────────────────────────────────

    def _decode(self, raw: bytes, resp=None) -> str:
        """Smart decode: respect Content-Type charset, then UTF-8, then ISO-8859-9."""
        if resp is not None:
            ct = resp.headers.get("Content-Type", "")
            if "charset=" in ct:
                charset = ct.split("charset=")[-1].split(";")[0].strip()
                try:
                    return raw.decode(charset)
                except (UnicodeDecodeError, LookupError):
                    pass
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode("iso-8859-9", errors="replace")

    def _get_locked(self, path: str, params: dict = None) -> str:
        """Perform a GET request — caller MUST hold self._lock."""
        url = f"{self.base_url}{path}"
        if params:
            url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v})
        try:
            resp = self.opener.open(url, timeout=self.timeout)
            return self._decode(resp.read(), resp)
        except urllib.error.HTTPError as exc:
            if exc.code in (302, 303, 301):
                # Session expired — try once more with a fresh login
                self._logged_in = False
                try:
                    self._login_locked()
                    resp = self.opener.open(url, timeout=self.timeout)
                    return self._decode(resp.read(), resp)
                except Exception:
                    raise SessionExpired(f"Session expired (HTTP {exc.code})") from exc
            raise SessionError(f"GET {path} failed: HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise SessionError(f"GET {path} failed: {exc.reason}") from exc

    def get(self, path: str, params: dict = None) -> str:
        """Perform a GET request through the VipUber session (thread-safe)."""
        with self._lock:
            self._ensure_login_locked()
            return self._get_locked(path, params)

    def _post_locked(self, path: str, data: dict) -> str:
        """Perform a POST request — caller MUST hold self._lock."""
        encoded = urllib.parse.urlencode(data, encoding="iso-8859-9").encode("iso-8859-9")
        try:
            resp = self.opener.open(f"{self.base_url}{path}", encoded, timeout=self.timeout)
            return self._decode(resp.read(), resp)
        except urllib.error.HTTPError as exc:
            if exc.code in (302, 303, 301):
                # Session expired — try once more with a fresh login
                self._logged_in = False
                try:
                    self._login_locked()
                    resp = self.opener.open(f"{self.base_url}{path}", encoded, timeout=self.timeout)
                    return self._decode(resp.read(), resp)
                except Exception:
                    raise SessionExpired(f"Session expired (HTTP {exc.code})") from exc
            raise SessionError(f"POST {path} failed: HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise SessionError(f"POST {path} failed: {exc.reason}") from exc

    def post(self, path: str, data: dict) -> str:
        """Perform a POST request through the VipUber session (thread-safe)."""
        with self._lock:
            self._ensure_login_locked()
            return self._post_locked(path, data)


# ── global session registry ──────────────────────────────

_sessions: dict[tuple[str, str], VipUberSession] = {}
_sessions_lock = threading.Lock()


def _session_key(email: str, password: str) -> tuple[str, str]:
    normalized_email = email.strip().lower()
    password_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return normalized_email, password_hash


def get_session(email: str = None, password: str = None) -> VipUberSession:
    """Get or create a session for the given credentials.

    Uses the configured default credentials when called without arguments.
    Thread-safe: protects the global session dict with a lock.
    """
    settings = get_settings()
    email = (email or settings.email).strip()
    password = password or settings.password

    key = _session_key(email, password)
    with _sessions_lock:
        session = _sessions.get(key)
        if session is None:
            session = VipUberSession(
                email=email,
                password=password,
                base_url=settings.base_url,
                customer_id=settings.customer_id,
                timeout=settings.request_timeout,
            )
            _sessions[key] = session
        return session


def login(email: str = None, password: str = None) -> dict:
    """Explicitly log in and return session info."""
    s = get_session(email, password)
    s.login()
    return {
        "status": "ok",
        "message": "Logged in successfully",
        "email": s.email,
        "session_active": True,
    }
