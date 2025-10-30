import os
import re
import uuid
import hashlib
import jwt  # PyJWT
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional, Literal, Dict, Any, Tuple

from dotenv import load_dotenv
import mysql.connector
from mysql.connector import errors as mysql_errors
from fastapi import FastAPI, HTTPException, Depends, status, Header, Request
from fastapi.security import OAuth2PasswordBearer
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from starlette.middleware.base import BaseHTTPMiddleware

print("Now UTC:", datetime.now(timezone.utc).isoformat())



# ------------------ Load env ------------------
load_dotenv()
DB_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("MYSQL_PORT", "3306"))
DB_USER = os.getenv("MYSQL_USER", "root")
DB_PASS = os.getenv("MYSQL_PASSWORD", "")
DB_NAME = os.getenv("MYSQL_DB", "fitness_app_sl")  # đổi theo DB của bạn

# JWT env
JWT_SECRET = os.getenv("JWT_SECRET", "change_me_super_secret")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_MINUTES", "60"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_DAYS", "7"))

# ------------------ Regex/Constants -----------------
EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
GOAL_TYPES = ("lose_weight", "stay_active", "reduce_stress")
UI_LANGS = ("en", "vi")  # cho phép mở rộng thêm nếu cần

# ------------------ FastAPI -----------------
app = FastAPI(title="Users API (Fitness)", version="1.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5500", "http://127.0.0.1:5500"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ====== Middleware: log headers (debug) ======
class LogHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Comment dòng dưới nếu không muốn log
        # print("[DEBUG] Incoming Request Headers:", dict(request.headers))
        response = await call_next(request)
        return response

app.add_middleware(LogHeadersMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5501", "http://localhost:5501",
        "http://127.0.0.1:5500", "http://localhost:5500",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------ DB Helpers -----------------
def get_conn():
    return mysql.connector.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS, database=DB_NAME
    )

def table_exists(cur, table_name: str) -> bool:
    cur.execute("SHOW TABLES LIKE %s", (table_name,))
    return cur.fetchone() is not None

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)

def _epoch(dt: datetime) -> int:
    return int(dt.timestamp())

# ------------------ Password helpers -----------------
def hash_sha256(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()

def verify_password(plain: str, hashed: str) -> bool:
    return hash_sha256(plain) == hashed

# ------------------ JWT helpers -----------------
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
REVOKED_JTI: set[str] = set()

def create_token(sub: str, kind: Literal["access", "refresh"], extra_claims: Dict[str, Any] | None = None) -> Tuple[str, int, str]:
    jti = str(uuid.uuid4())
    iat = _now_utc()
    exp = iat + (timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES) if kind == "access" else timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))
    payload: Dict[str, Any] = {
        "sub": sub,
        "jti": jti,
        "iat": _epoch(iat),
        "exp": _epoch(exp),
        "type": kind,
    }
    if extra_claims:
        payload.update(extra_claims)
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token, _epoch(exp), jti

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            leeway=60  # cho phép lệch clock nhẹ
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")

def ensure_not_revoked(jti: str):
    if jti in REVOKED_JTI:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has been revoked")

# ------------------ Pydantic Schemas -----------------
class UserItem(BaseModel):
    user_id: int
    full_name: str
    email: str
    height_cm: Optional[float] = None
    start_weight_kg: Optional[float] = None
    goal_type: Literal["lose_weight", "stay_active", "reduce_stress"]
    goal_target_weight_kg: Optional[float] = None
    timezone: str
    ui_language: str
    notifications_enabled: bool
    created_at: datetime

class CreateUserRequest(BaseModel):
    full_name: str = Field(..., min_length=3, max_length=120)
    email: str
    password: str = Field(..., min_length=8)
    height_cm: Optional[float] = Field(None, description="120–250 (cm)")
    start_weight_kg: Optional[float] = Field(None, description="30–300 (kg)")
    goal_type: Literal["lose_weight", "stay_active", "reduce_stress"] = "lose_weight"
    goal_target_weight_kg: Optional[float] = Field(None, description="30–300 (kg)")
    timezone: str = "Asia/Ho_Chi_Minh"
    ui_language: str = "en"
    notifications_enabled: bool = True

    @validator("email")
    def _check_email(cls, v: str):
        v = v.strip()
        if not EMAIL_RE.match(v):
            raise ValueError("Invalid email format")
        return v

    @validator("height_cm")
    def _check_height(cls, v):
        if v is not None and not (120 <= v <= 250):
            raise ValueError("height_cm must be between 120 and 250")
        return v

    @validator("start_weight_kg")
    def _check_start_weight(cls, v):
        if v is not None and not (30 <= v <= 300):
            raise ValueError("start_weight_kg must be between 30 and 300")
        return v

    @validator("goal_target_weight_kg")
    def _check_goal_weight(cls, v):
        if v is not None and not (30 <= v <= 300):
            raise ValueError("goal_target_weight_kg must be between 30 and 300")
        return v

    @validator("ui_language")
    def _check_lang(cls, v):
        return v.strip()

class UpdateUserRequest(BaseModel):
    full_name: Optional[str] = Field(None, min_length=3, max_length=120)
    email: Optional[str] = None
    password: Optional[str] = Field(None, min_length=8)
    height_cm: Optional[float] = None
    start_weight_kg: Optional[float] = None
    goal_type: Optional[Literal["lose_weight", "stay_active", "reduce_stress"]] = None
    goal_target_weight_kg: Optional[float] = None
    timezone: Optional[str] = None
    ui_language: Optional[str] = None
    notifications_enabled: Optional[bool] = None

    @validator("email")
    def _check_email(cls, v):
        if v is None:
            return v
        v = v.strip()
        if not EMAIL_RE.match(v):
            raise ValueError("Invalid email format")
        return v

    @validator("height_cm")
    def _check_height(cls, v):
        if v is not None and not (120 <= v <= 250):
            raise ValueError("height_cm must be between 120 and 250")
        return v

    @validator("start_weight_kg")
    def _check_start_weight(cls, v):
        if v is not None and not (30 <= v <= 300):
            raise ValueError("start_weight_kg must be between 30 and 300")
        return v

    @validator("goal_target_weight_kg")
    def _check_goal_weight(cls, v):
        if v is not None and not (30 <= v <= 300):
            raise ValueError("goal_target_weight_kg must be between 30 and 300")
        return v

# ---- Auth Schemas ----
class LoginRequest(BaseModel):
    identifier: str = Field(..., description="email (hoặc cho phép full_name trong tương lai)")
    password: str = Field(..., min_length=8)

class TokenPairResponse(BaseModel):
    token_type: Literal["bearer"] = "bearer"
    access_token: str
    access_expires_at: int
    refresh_token: str
    refresh_expires_at: int

class RefreshRequest(BaseModel):
    refresh_token: str

class LogoutResponse(BaseModel):
    detail: str

# ------------------ Mappers -----------------
def _row_to_user_item(row: dict) -> UserItem:
    return UserItem(
        user_id=row["user_id"],
        full_name=row["full_name"],
        email=row["email"],
        height_cm=row.get("height_cm"),
        start_weight_kg=row.get("start_weight_kg"),
        goal_type=row["goal_type"],
        goal_target_weight_kg=row.get("goal_target_weight_kg"),
        timezone=row["timezone"],
        ui_language=row["ui_language"],
        notifications_enabled=bool(row["notifications_enabled"]),
        created_at=row["created_at"],
    )

# ------------------ Query helpers -----------------
def _fetch_user_by_email(cur, email: str) -> Optional[dict]:
    cur.execute(
        """
        SELECT
            user_id, full_name, email, password_hash,
            height_cm, start_weight_kg, goal_type, goal_target_weight_kg,
            timezone, ui_language, notifications_enabled, created_at
        FROM users
        WHERE email=%s
        LIMIT 1
        """,
        (email,),
    )
    return cur.fetchone()

def _fetch_user_by_id(cur, user_id: int) -> Optional[dict]:
    cur.execute(
        """
        SELECT
            user_id, full_name, email, password_hash,
            height_cm, start_weight_kg, goal_type, goal_target_weight_kg,
            timezone, ui_language, notifications_enabled, created_at
        FROM users
        WHERE user_id=%s
        LIMIT 1
        """,
        (user_id,),
    )
    return cur.fetchone()

def _email_exists(cur, email: str, exclude_user_id: Optional[int] = None) -> bool:
    if exclude_user_id:
        cur.execute("SELECT 1 FROM users WHERE email=%s AND user_id<>%s LIMIT 1", (email, exclude_user_id))
    else:
        cur.execute("SELECT 1 FROM users WHERE email=%s LIMIT 1", (email,))
    return cur.fetchone() is not None

# ------------------ Auth Dependencies -----------------
def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    payload = decode_token(token)
    ensure_not_revoked(payload.get("jti", ""))
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Not an access token")
    user_id = int(payload.get("sub"))
    # verify still exists
    try:
        cnx = get_conn()
        cur = cnx.cursor(dictionary=True)
        row = _fetch_user_by_id(cur, user_id)
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        return {"user_id": row["user_id"], "email": row["email"], "full_name": row["full_name"]}
    finally:
        try:
            cur.close(); cnx.close()
        except Exception:
            pass

# ------------------ CRUD APIs -----------------
@app.get("/api/users", response_model=List[UserItem])
def list_users():
    try:
        cnx = get_conn(); cur = cnx.cursor(dictionary=True)
        if not table_exists(cur, "users"):
            raise HTTPException(status_code=500, detail="Table `users` not found")
        cur.execute(
            """
            SELECT user_id, full_name, email, password_hash,
                   height_cm, start_weight_kg, goal_type, goal_target_weight_kg,
                   timezone, ui_language, notifications_enabled, created_at
            FROM users
            ORDER BY user_id ASC
            """
        )
        rows = cur.fetchall() or []
        return [_row_to_user_item(r) for r in rows]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")
    finally:
        try:
            cur.close(); cnx.close()
        except Exception:
            pass

@app.post("/api/users", response_model=UserItem, status_code=201)
def create_user(payload: CreateUserRequest):
    try:
        cnx = get_conn(); cur = cnx.cursor(dictionary=True)
        if not table_exists(cur, "users"):
            raise HTTPException(status_code=500, detail="Table `users` not found")

        # unique email
        if _email_exists(cur, payload.email):
            raise HTTPException(status_code=400, detail="Email already exists")

        pwd_hash = hash_sha256(payload.password)
        cur.execute(
            """
            INSERT INTO users
                (full_name, email, password_hash, height_cm, start_weight_kg, goal_type,
                 goal_target_weight_kg, timezone, ui_language, notifications_enabled)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                payload.full_name.strip(),
                payload.email.strip(),
                pwd_hash,
                payload.height_cm,
                payload.start_weight_kg,
                payload.goal_type,
                payload.goal_target_weight_kg,
                payload.timezone,
                payload.ui_language,
                1 if payload.notifications_enabled else 0,
            )
        )
        cnx.commit()
        new_id = cur.lastrowid
        row = _fetch_user_by_id(cur, new_id)
        return _row_to_user_item(row)
    except mysql_errors.IntegrityError as e:
        cnx.rollback()
        raise HTTPException(status_code=400, detail=f"Integrity error: {e.msg}")
    except Exception as e:
        cnx.rollback()
        raise HTTPException(status_code=500, detail=f"Create failed: {e}")
    finally:
        try:
            cur.close(); cnx.close()
        except Exception:
            pass

@app.get("/api/users/{user_id}", response_model=UserItem)
def get_user_by_id(user_id: int):
    try:
        cnx = get_conn(); cur = cnx.cursor(dictionary=True)
        row = _fetch_user_by_id(cur, user_id)
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        return _row_to_user_item(row)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")
    finally:
        try:
            cur.close(); cnx.close()
        except Exception:
            pass

@app.put("/api/users/{user_id}", response_model=UserItem)
def update_user(user_id: int, payload: UpdateUserRequest):
    try:
        cnx = get_conn(); cur = cnx.cursor(dictionary=True)
        row = _fetch_user_by_id(cur, user_id)
        if not row:
            raise HTTPException(status_code=404, detail="User not found")

        # email unique check nếu cập nhật email
        if payload.email and _email_exists(cur, payload.email, exclude_user_id=user_id):
            raise HTTPException(status_code=400, detail="Email already exists")

        sets = []
        vals = []

        def add_set(col: str, val):
            sets.append(f"{col}=%s"); vals.append(val)

        if payload.full_name is not None: add_set("full_name", payload.full_name.strip())
        if payload.email is not None: add_set("email", payload.email.strip())
        if payload.password is not None: add_set("password_hash", hash_sha256(payload.password))
        if payload.height_cm is not None: add_set("height_cm", payload.height_cm)
        if payload.start_weight_kg is not None: add_set("start_weight_kg", payload.start_weight_kg)
        if payload.goal_type is not None: add_set("goal_type", payload.goal_type)
        if payload.goal_target_weight_kg is not None: add_set("goal_target_weight_kg", payload.goal_target_weight_kg)
        if payload.timezone is not None: add_set("timezone", payload.timezone)
        if payload.ui_language is not None: add_set("ui_language", payload.ui_language)
        if payload.notifications_enabled is not None: add_set("notifications_enabled", 1 if payload.notifications_enabled else 0)

        if not sets:
            # Không có trường nào để cập nhật -> trả về bản ghi hiện tại
            return _row_to_user_item(row)

        sql = f"UPDATE users SET {', '.join(sets)} WHERE user_id=%s"
        vals.append(user_id)
        cur.execute(sql, tuple(vals))
        cnx.commit()

        row2 = _fetch_user_by_id(cur, user_id)
        return _row_to_user_item(row2)
    except HTTPException:
        raise
    except Exception as e:
        cnx.rollback()
        raise HTTPException(status_code=500, detail=f"Update failed: {e}")
    finally:
        try:
            cur.close(); cnx.close()
        except Exception:
            pass

@app.delete("/api/users/{user_id}")
def delete_user(user_id: int):
    try:
        cnx = get_conn(); cur = cnx.cursor(dictionary=True)
        cur.execute("DELETE FROM users WHERE user_id=%s", (user_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="User not found")
        cnx.commit()
        return {"detail": "User deleted successfully."}
    except HTTPException:
        raise
    except Exception as e:
        cnx.rollback()
        raise HTTPException(status_code=500, detail=f"Delete failed: {e}")
    finally:
        try:
            cur.close(); cnx.close()
        except Exception:
            pass

# ------------------ Auth (JWT) -----------------
@app.post("/api/auth/login", response_model=TokenPairResponse)
def login(payload: LoginRequest):
    try:
        cnx = get_conn(); cur = cnx.cursor(dictionary=True)
        # hiện tại login qua email
        user = _fetch_user_by_email(cur, payload.identifier.strip())
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        if not verify_password(payload.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        access_token, access_exp, _ = create_token(
            sub=str(user["user_id"]),
            kind="access",
            extra_claims={"email": user["email"], "full_name": user["full_name"]}
        )
        refresh_token, refresh_exp, _ = create_token(sub=str(user["user_id"]), kind="refresh")

        return TokenPairResponse(
            access_token=access_token,
            access_expires_at=access_exp,
            refresh_token=refresh_token,
            refresh_expires_at=refresh_exp,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Login failed: {e}")
    finally:
        try:
            cur.close(); cnx.close()
        except Exception:
            pass

@app.post("/api/auth/refresh", response_model=TokenPairResponse)
def refresh_token(payload: RefreshRequest):
    data = decode_token(payload.refresh_token)
    ensure_not_revoked(data.get("jti", ""))
    if data.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Not a refresh token")
    user_id = int(data.get("sub"))

    # rotate refresh: revoke old
    old_jti = data.get("jti")
    if old_jti:
        REVOKED_JTI.add(old_jti)

    try:
        cnx = get_conn(); cur = cnx.cursor(dictionary=True)
        user = _fetch_user_by_id(cur, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        access_token, access_exp, _ = create_token(
            sub=str(user_id),
            kind="access",
            extra_claims={"email": user["email"], "full_name": user["full_name"]}
        )
        new_refresh, refresh_exp, _ = create_token(sub=str(user_id), kind="refresh")
        return TokenPairResponse(
            access_token=access_token,
            access_expires_at=access_exp,
            refresh_token=new_refresh,
            refresh_expires_at=refresh_exp,
        )
    finally:
        try:
            cur.close(); cnx.close()
        except Exception:
            pass

@app.post("/api/auth/logout", response_model=LogoutResponse)
def logout(authorization: str = Header(None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=400, detail="Missing Bearer token in Authorization header")
    token = authorization.split(" ", 1)[1].strip()
    data = decode_token(token)
    jti = data.get("jti")
    if not jti:
        raise HTTPException(status_code=400, detail="Token missing jti")
    REVOKED_JTI.add(jti)
    return LogoutResponse(detail="Logged out (access token revoked).")

@app.get("/api/me", response_model=UserItem)
def read_me(current=Depends(get_current_user)):
    try:
        cnx = get_conn(); cur = cnx.cursor(dictionary=True)
        row = _fetch_user_by_id(cur, int(current["user_id"]))
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        return _row_to_user_item(row)
    finally:
        try:
            cur.close(); cnx.close()
        except Exception:
            pass

# ------------------ Dev runner ------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("user:app", host="0.0.0.0", port=8000, reload=True)
