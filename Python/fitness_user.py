import os
import re
import uuid
import hashlib
from datetime import datetime, timezone, timedelta, date
from typing import List, Optional, Any, Dict, Tuple, Literal

from dotenv import load_dotenv
import mysql.connector
from fastapi import FastAPI, HTTPException, Depends, status, Header, Request
from fastapi.security import OAuth2PasswordBearer
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
import jwt  # PyJWT

load_dotenv()

# DB config (reuse env conventions)
DB_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("MYSQL_PORT", "3306"))
DB_USER = os.getenv("MYSQL_USER", "root")
DB_PASS = os.getenv("MYSQL_PASSWORD", "")
DB_NAME = os.getenv("MYSQL_DB", "app_db")

# JWT config
JWT_SECRET = os.getenv("JWT_SECRET", "change_me_super_secret")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_MINUTES", "60"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_DAYS", "7"))

# Regex
EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

app = FastAPI(title="Fitness Users API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5500", "http://127.0.0.1:5500"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_conn():
    return mysql.connector.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS, database=DB_NAME
    )


def table_exists(cur, table_name: str) -> bool:
    cur.execute("SHOW TABLES LIKE %s", (table_name,))
    return cur.fetchone() is not None


def get_columns(cur, table_name: str) -> set:
    cur.execute(f"DESCRIBE `{table_name}`")
    rows = cur.fetchall() or []
    if not rows:
        return set()
    if not isinstance(rows[0], dict):
        return {r[0] for r in rows}
    return {r.get("Field") for r in rows if "Field" in r}


def hash_sha256(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def verify_password(plain: str, hashed: str) -> bool:
    return hash_sha256(plain) == hashed


def _epoch(dt: datetime) -> int:
    return int(dt.timestamp())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_token(sub: str, kind: Literal["access", "refresh"], extra_claims: Dict[str, Any] | None = None) -> Tuple[str, int, str]:
    jti = str(uuid.uuid4())
    iat = _now()
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
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM], options={"require": ["exp", "iat", "sub"]})
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


# Simple in-memory revoked set (process-lifetime)
REVOKED_JTI: set[str] = set()


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/fitness/auth/login")


class CreateUserRequest(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=120)
    email: str
    password: Optional[str] = Field(None, min_length=8)
    height_cm: Optional[float] = None
    start_weight_kg: Optional[float] = None
    goal_type: Optional[Literal["lose_weight", "stay_active", "reduce_stress"]] = "lose_weight"
    goal_target_weight_kg: Optional[float] = None
    timezone: Optional[str] = "Asia/Ho_Chi_Minh"
    ui_language: Optional[str] = "en"
    notifications_enabled: Optional[bool] = True

    @validator("email")
    def _check_email(cls, v: str):
        v = v.strip()
        if not EMAIL_RE.match(v):
            raise ValueError("Invalid email format")
        return v


class UserItem(BaseModel):
    user_id: int
    full_name: str
    email: str
    height_cm: Optional[float] = None
    start_weight_kg: Optional[float] = None
    goal_type: str
    goal_target_weight_kg: Optional[float] = None
    timezone: str
    ui_language: str
    notifications_enabled: bool
    created_at: Optional[datetime] = None


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenPairResponse(BaseModel):
    token_type: Literal["bearer"] = "bearer"
    access_token: str
    access_expires_at: int
    refresh_token: str
    refresh_expires_at: int


def find_user_by_id(cur, user_id: int) -> Optional[dict]:
    cur.execute("SELECT * FROM `users` WHERE user_id=%s LIMIT 1", (user_id,))
    return cur.fetchone()


def email_exists(cur, email: str, exclude_id: Optional[int] = None) -> bool:
    q = "SELECT 1 FROM `users` WHERE email=%s"
    params = [email]
    if exclude_id:
        q += " AND user_id<>%s"
        params.append(exclude_id)
    q += " LIMIT 1"
    cur.execute(q, tuple(params))
    return cur.fetchone() is not None


@app.get("/api/fitness/users", response_model=List[UserItem])
def list_users():
    try:
        cnx = get_conn()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB connect failed: {e}")
    try:
        cur = cnx.cursor(dictionary=True)
        if not table_exists(cur, "users"):
            raise HTTPException(status_code=500, detail="Table `users` not found")
        cols = get_columns(cur, "users")
        # build select with available columns
        select_fields = ["user_id", "full_name", "email", "height_cm", "start_weight_kg",
                         "goal_type", "goal_target_weight_kg", "timezone", "ui_language", "notifications_enabled", "created_at"]
        sql = "SELECT " + ", ".join([f"{c}" for c in select_fields if c in cols or c in ("user_id","full_name","email")]) + " FROM `users` ORDER BY user_id ASC"
        cur.execute(sql)
        rows = cur.fetchall()
        result = []
        for r in rows:
            result.append(UserItem(
                user_id=r.get("user_id"),
                full_name=r.get("full_name"),
                email=r.get("email"),
                height_cm=r.get("height_cm"),
                start_weight_kg=r.get("start_weight_kg"),
                goal_type=r.get("goal_type"),
                goal_target_weight_kg=r.get("goal_target_weight_kg"),
                timezone=r.get("timezone") or "Asia/Ho_Chi_Minh",
                ui_language=r.get("ui_language") or "en",
                notifications_enabled=bool(r.get("notifications_enabled")) if r.get("notifications_enabled") is not None else True,
                created_at=r.get("created_at"),
            ))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")
    finally:
        try:
            cur.close(); cnx.close()
        except Exception:
            pass


@app.post("/api/fitness/users", response_model=UserItem, status_code=201)
def create_user(payload: CreateUserRequest):
    try:
        cnx = get_conn()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB connect failed: {e}")
    try:
        cur = cnx.cursor(dictionary=True)
        if not table_exists(cur, "users"):
            raise HTTPException(status_code=500, detail="Table `users` not found")
        cols = get_columns(cur, "users")
        if email_exists(cur, payload.email):
            raise HTTPException(status_code=400, detail="Email already exists")

        # build insert based on available columns
        fields = ["full_name", "email"]
        values = [payload.full_name, payload.email]
        if "height_cm" in cols:
            fields.append("height_cm"); values.append(payload.height_cm)
        if "start_weight_kg" in cols:
            fields.append("start_weight_kg"); values.append(payload.start_weight_kg)
        if "goal_type" in cols:
            fields.append("goal_type"); values.append(payload.goal_type)
        if "goal_target_weight_kg" in cols:
            fields.append("goal_target_weight_kg"); values.append(payload.goal_target_weight_kg)
        if "timezone" in cols:
            fields.append("timezone"); values.append(payload.timezone)
        if "ui_language" in cols:
            fields.append("ui_language"); values.append(payload.ui_language)
        if "notifications_enabled" in cols:
            fields.append("notifications_enabled"); values.append(1 if payload.notifications_enabled else 0)

        # optional password storage - only if column exists
        has_password = "PasswordHash" in cols or "password_hash" in cols
        password_col = "PasswordHash" if "PasswordHash" in cols else ("password_hash" if "password_hash" in cols else None)
        if payload.password:
            if not has_password:
                # We still allow create without password, but inform user in response via exception
                raise HTTPException(status_code=501, detail="Database does not have a password column (PasswordHash). Create user without password or add PasswordHash column to enable auth.")
            fields.append(password_col); values.append(hash_sha256(payload.password))

        placeholders = ", ".join(["%s"] * len(values))
        sql = f"INSERT INTO `users` ({', '.join(fields)}) VALUES ({placeholders})"
        cur.execute(sql, tuple(values))
        cnx.commit()
        new_id = cur.lastrowid
        # return created
        cur.execute("SELECT * FROM `users` WHERE user_id=%s LIMIT 1", (new_id,))
        row = cur.fetchone()
        return UserItem(
            user_id=row.get("user_id"),
            full_name=row.get("full_name"),
            email=row.get("email"),
            height_cm=row.get("height_cm"),
            start_weight_kg=row.get("start_weight_kg"),
            goal_type=row.get("goal_type"),
            goal_target_weight_kg=row.get("goal_target_weight_kg"),
            timezone=row.get("timezone") or "Asia/Ho_Chi_Minh",
            ui_language=row.get("ui_language") or "en",
            notifications_enabled=bool(row.get("notifications_enabled")) if row.get("notifications_enabled") is not None else True,
            created_at=row.get("created_at"),
        )
    except HTTPException:
        cnx.rollback()
        raise
    except Exception as e:
        cnx.rollback()
        raise HTTPException(status_code=500, detail=f"Create failed: {e}")
    finally:
        try:
            cur.close(); cnx.close()
        except Exception:
            pass


@app.get("/api/fitness/users/{user_id}", response_model=UserItem)
def get_user(user_id: int):
    try:
        cnx = get_conn()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB connect failed: {e}")
    try:
        cur = cnx.cursor(dictionary=True)
        row = find_user_by_id(cur, user_id)
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        return UserItem(
            user_id=row.get("user_id"),
            full_name=row.get("full_name"),
            email=row.get("email"),
            height_cm=row.get("height_cm"),
            start_weight_kg=row.get("start_weight_kg"),
            goal_type=row.get("goal_type"),
            goal_target_weight_kg=row.get("goal_target_weight_kg"),
            timezone=row.get("timezone") or "Asia/Ho_Chi_Minh",
            ui_language=row.get("ui_language") or "en",
            notifications_enabled=bool(row.get("notifications_enabled")) if row.get("notifications_enabled") is not None else True,
            created_at=row.get("created_at"),
        )
    finally:
        try:
            cur.close(); cnx.close()
        except Exception:
            pass


@app.put("/api/fitness/users/{user_id}", response_model=UserItem)
def update_user(user_id: int, payload: CreateUserRequest):
    try:
        cnx = get_conn()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB connect failed: {e}")
    try:
        cur = cnx.cursor(dictionary=True)
        row = find_user_by_id(cur, user_id)
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        if email_exists(cur, payload.email, exclude_id=user_id):
            raise HTTPException(status_code=400, detail="Email already exists")

        cols = get_columns(cur, "users")
        sets = ["full_name=%s", "email=%s"]
        values = [payload.full_name, payload.email]
        if "height_cm" in cols:
            sets.append("height_cm=%s"); values.append(payload.height_cm)
        if "start_weight_kg" in cols:
            sets.append("start_weight_kg=%s"); values.append(payload.start_weight_kg)
        if "goal_type" in cols:
            sets.append("goal_type=%s"); values.append(payload.goal_type)
        if "goal_target_weight_kg" in cols:
            sets.append("goal_target_weight_kg=%s"); values.append(payload.goal_target_weight_kg)
        if "timezone" in cols:
            sets.append("timezone=%s"); values.append(payload.timezone)
        if "ui_language" in cols:
            sets.append("ui_language=%s"); values.append(payload.ui_language)
        if "notifications_enabled" in cols:
            sets.append("notifications_enabled=%s"); values.append(1 if payload.notifications_enabled else 0)

        password_col = "PasswordHash" if "PasswordHash" in cols else ("password_hash" if "password_hash" in cols else None)
        if payload.password:
            if not password_col:
                raise HTTPException(status_code=501, detail="Database does not have a password column (PasswordHash). Add it to enable password updates.")
            sets.append(f"{password_col}=%s"); values.append(hash_sha256(payload.password))

        values.append(user_id)
        sql = f"UPDATE `users` SET {', '.join(sets)} WHERE user_id=%s"
        cur.execute(sql, tuple(values))
        cnx.commit()
        cur.execute("SELECT * FROM `users` WHERE user_id=%s LIMIT 1", (user_id,))
        r = cur.fetchone()
        return UserItem(
            user_id=r.get("user_id"),
            full_name=r.get("full_name"),
            email=r.get("email"),
            height_cm=r.get("height_cm"),
            start_weight_kg=r.get("start_weight_kg"),
            goal_type=r.get("goal_type"),
            goal_target_weight_kg=r.get("goal_target_weight_kg"),
            timezone=r.get("timezone") or "Asia/Ho_Chi_Minh",
            ui_language=r.get("ui_language") or "en",
            notifications_enabled=bool(r.get("notifications_enabled")) if r.get("notifications_enabled") is not None else True,
            created_at=r.get("created_at"),
        )
    except HTTPException:
        cnx.rollback()
        raise
    except Exception as e:
        cnx.rollback()
        raise HTTPException(status_code=500, detail=f"Update failed: {e}")
    finally:
        try:
            cur.close(); cnx.close()
        except Exception:
            pass


@app.delete("/api/fitness/users/{user_id}")
def delete_user(user_id: int):
    try:
        cnx = get_conn()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB connect failed: {e}")
    try:
        cur = cnx.cursor()
        cur.execute("DELETE FROM `users` WHERE user_id=%s", (user_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="User not found")
        cnx.commit()
        return {"detail": "User deleted successfully."}
    except HTTPException:
        cnx.rollback()
        raise
    except Exception as e:
        cnx.rollback()
        raise HTTPException(status_code=500, detail=f"Delete failed: {e}")
    finally:
        try:
            cur.close(); cnx.close()
        except Exception:
            pass


def _fetch_user_by_email(cur, email: str) -> Optional[dict]:
    cur.execute("SELECT * FROM `users` WHERE email=%s LIMIT 1", (email,))
    return cur.fetchone()


def ensure_not_revoked(jti: str):
    if jti in REVOKED_JTI:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has been revoked")


def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    payload = decode_token(token)
    ensure_not_revoked(payload.get("jti", ""))
    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not an access token")
    user_id = int(payload.get("sub"))
    try:
        cnx = get_conn()
        cur = cnx.cursor(dictionary=True)
        row = find_user_by_id(cur, user_id)
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        return {"user_id": row["user_id"], "email": row["email"], "full_name": row["full_name"]}
    finally:
        try:
            cur.close(); cnx.close()
        except Exception:
            pass


@app.post("/api/fitness/auth/login", response_model=TokenPairResponse)
def login(payload: LoginRequest):
    try:
        cnx = get_conn()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB connect failed: {e}")
    try:
        cur = cnx.cursor(dictionary=True)
        u = _fetch_user_by_email(cur, payload.email)
        if not u:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        # must have password column
        password_col = "PasswordHash" if "PasswordHash" in u or "PasswordHash" in get_columns(cur, "users") else ("password_hash" if "password_hash" in u or "password_hash" in get_columns(cur, "users") else None)
        if not password_col:
            raise HTTPException(status_code=501, detail="Auth not enabled: users table does not have a password column (PasswordHash). Add it to enable login.")
        pwd_hash = u.get(password_col) if password_col in u else u.get("PasswordHash") or u.get("password_hash")
        if not verify_password(payload.password, pwd_hash):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        access_token, access_exp, _ = create_token(sub=str(u["user_id"]), kind="access", extra_claims={"email": u["email"]})
        refresh_token, refresh_exp, _ = create_token(sub=str(u["user_id"]), kind="refresh")
        return TokenPairResponse(
            access_token=access_token,
            access_expires_at=access_exp,
            refresh_token=refresh_token,
            refresh_expires_at=refresh_exp,
        )
    finally:
        try:
            cur.close(); cnx.close()
        except Exception:
            pass


@app.post("/api/fitness/auth/refresh", response_model=TokenPairResponse)
def refresh_token(payload: Dict[str, str]):
    token = payload.get("refresh_token") if isinstance(payload, dict) else None
    if not token:
        raise HTTPException(status_code=400, detail="Missing refresh_token in body")
    data = decode_token(token)
    ensure_not_revoked(data.get("jti", ""))
    if data.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Not a refresh token")
    user_id = int(data.get("sub"))
    # revoke old refresh
    old_jti = data.get("jti")
    if old_jti:
        REVOKED_JTI.add(old_jti)
    try:
        cnx = get_conn(); cur = cnx.cursor(dictionary=True)
        row = find_user_by_id(cur, user_id)
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        email = row["email"]
    finally:
        try:
            cur.close(); cnx.close()
        except Exception:
            pass
    access_token, access_exp, _ = create_token(sub=str(user_id), kind="access", extra_claims={"email": email})
    new_refresh, refresh_exp, _ = create_token(sub=str(user_id), kind="refresh")
    return TokenPairResponse(
        access_token=access_token,
        access_expires_at=access_exp,
        refresh_token=new_refresh,
        refresh_expires_at=refresh_exp,
    )


@app.post("/api/fitness/auth/logout")
def logout(authorization: str = Header(None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=400, detail="Missing Bearer token in Authorization header")
    token = authorization.split(" ", 1)[1].strip()
    data = decode_token(token)
    jti = data.get("jti")
    if jti:
        REVOKED_JTI.add(jti)
    return {"detail": "Logged out (access token revoked)."}


@app.get("/api/fitness/me", response_model=UserItem)
def read_me(current=Depends(get_current_user)):
    try:
        cnx = get_conn(); cur = cnx.cursor(dictionary=True)
        row = find_user_by_id(cur, int(current["user_id"]))
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        return UserItem(
            user_id=row.get("user_id"),
            full_name=row.get("full_name"),
            email=row.get("email"),
            height_cm=row.get("height_cm"),
            start_weight_kg=row.get("start_weight_kg"),
            goal_type=row.get("goal_type"),
            goal_target_weight_kg=row.get("goal_target_weight_kg"),
            timezone=row.get("timezone") or "Asia/Ho_Chi_Minh",
            ui_language=row.get("ui_language") or "en",
            notifications_enabled=bool(row.get("notifications_enabled")) if row.get("notifications_enabled") is not None else True,
            created_at=row.get("created_at"),
        )
    finally:
        try:
            cur.close(); cnx.close()
        except Exception:
            pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("fitness_user:app", host="0.0.0.0", port=8001, reload=True)
