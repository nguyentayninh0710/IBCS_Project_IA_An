# workouts.py — Fitness Workouts API (CRUD + JWT guard)
import os
import re
import uuid
import hashlib
import jwt  # PyJWT
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Literal, Dict, Any, Tuple

from dotenv import load_dotenv
import mysql.connector
from mysql.connector import errors as mysql_errors
from fastapi import FastAPI, HTTPException, Depends, status, Header, Request, Query
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
DB_NAME = os.getenv("MYSQL_DB", "fitness_app_sl")

# JWT env (same style as user.py)
JWT_SECRET = os.getenv("JWT_SECRET", "change_me_super_secret")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_MINUTES", "60"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_DAYS", "7"))

# ------------------ Constants -----------------
WORKOUT_TYPES = ("cardio", "strength", "mixed")
INTENSITIES = ("low", "medium", "high")
LEVELS = ("beginner", "intermediate")

# ------------------ FastAPI -----------------
app = FastAPI(title="Workouts API (Fitness)", version="1.0")

# CORS (giống user.py)
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

# ====== Middleware: optional request header log ======
class LogHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # print("[DEBUG] Incoming Request Headers:", dict(request.headers))
        response = await call_next(request)
        return response

app.add_middleware(LogHeadersMiddleware)

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

# ------------------ JWT helpers (same pattern) -----------------
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
        # not used directly here, but kept identical to user.py for parity
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
            leeway=60
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")

def ensure_not_revoked(jti: str):
    if jti in REVOKED_JTI:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has been revoked")

def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    payload = decode_token(token)
    ensure_not_revoked(payload.get("jti", ""))
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Not an access token")
    user_id = int(payload.get("sub"))
    # verify user still exists (avoid dangling FK)
    try:
        cnx = get_conn()
        cur = cnx.cursor(dictionary=True)
        cur.execute("SELECT user_id, email, full_name FROM users WHERE user_id=%s LIMIT 1", (user_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        return {"user_id": row["user_id"], "email": row.get("email"), "full_name": row.get("full_name")}
    finally:
        try:
            cur.close(); cnx.close()
        except Exception:
            pass

# ------------------ Pydantic Schemas -----------------
class WorkoutItem(BaseModel):
    workout_id: int
    name: str
    type: Literal["cardio", "strength", "mixed"]
    intensity: Literal["low", "medium", "high"]
    estimated_minutes: int
    level: Literal["beginner", "intermediate"]
    created_by: Optional[int] = None  # FK -> users.user_id

class CreateWorkoutRequest(BaseModel):
    name: str = Field(..., min_length=3, max_length=120)
    type: Literal["cardio", "strength", "mixed"]
    intensity: Literal["low", "medium", "high"] = "low"
    estimated_minutes: int = Field(..., ge=5, le=30, description="5–30 minutes")
    level: Literal["beginner", "intermediate"] = "beginner"
    created_by: Optional[int] = Field(None, description="If omitted, will use current user")

    @validator("name")
    def _trim_name(cls, v):
        return v.strip()

class UpdateWorkoutRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=3, max_length=120)
    type: Optional[Literal["cardio", "strength", "mixed"]] = None
    intensity: Optional[Literal["low", "medium", "high"]] = None
    estimated_minutes: Optional[int] = Field(None, ge=5, le=30)
    level: Optional[Literal["beginner", "intermediate"]] = None
    created_by: Optional[int] = None  # allow reassignment (will check FK)

    @validator("name")
    def _trim_name(cls, v):
        return v.strip() if v is not None else v

# ------------------ Row mappers -----------------
def _row_to_workout_item(row: dict) -> WorkoutItem:
    return WorkoutItem(
        workout_id=row["workout_id"],
        name=row["name"],
        type=row["type"],
        intensity=row["intensity"],
        estimated_minutes=int(row["estimated_minutes"]),
        level=row["level"],
        created_by=row.get("created_by"),
    )

# ------------------ Query helpers -----------------
def _fetch_workout_by_id(cur, workout_id: int) -> Optional[dict]:
    cur.execute(
        """
        SELECT workout_id, name, type, intensity, estimated_minutes, level, created_by
        FROM workouts
        WHERE workout_id=%s
        LIMIT 1
        """,
        (workout_id,),
    )
    return cur.fetchone()

def _user_exists(cur, user_id: int) -> bool:
    cur.execute("SELECT 1 FROM users WHERE user_id=%s LIMIT 1", (user_id,))
    return cur.fetchone() is not None

# ------------------ CRUD APIs -----------------
@app.get("/api/workouts", response_model=List[WorkoutItem])
def list_workouts(
    q: Optional[str] = Query(None, description="search by name (contains)"),
    type: Optional[Literal["cardio", "strength", "mixed"]] = Query(None),
    intensity: Optional[Literal["low", "medium", "high"]] = Query(None),
    level: Optional[Literal["beginner", "intermediate"]] = Query(None),
):
    try:
        cnx = get_conn(); cur = cnx.cursor(dictionary=True)
        if not table_exists(cur, "workouts"):
            raise HTTPException(status_code=500, detail="Table `workouts` not found")

        clauses = []
        vals: list[Any] = []

        if q:
            clauses.append("name LIKE %s"); vals.append(f"%{q.strip()}%")
        if type:
            clauses.append("type=%s"); vals.append(type)
        if intensity:
            clauses.append("intensity=%s"); vals.append(intensity)
        if level:
            clauses.append("level=%s"); vals.append(level)

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        cur.execute(
            f"""
            SELECT workout_id, name, type, intensity, estimated_minutes, level, created_by
            FROM workouts
            {where_sql}
            ORDER BY workout_id ASC
            """,
            tuple(vals)
        )
        rows = cur.fetchall() or []
        return [_row_to_workout_item(r) for r in rows]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")
    finally:
        try:
            cur.close(); cnx.close()
        except Exception:
            pass

@app.post("/api/workouts", response_model=WorkoutItem, status_code=201)
def create_workout(payload: CreateWorkoutRequest, current=Depends(get_current_user)):
    try:
        cnx = get_conn(); cur = cnx.cursor(dictionary=True)
        if not table_exists(cur, "workouts"):
            raise HTTPException(status_code=500, detail="Table `workouts` not found")

        creator_id = payload.created_by if payload.created_by is not None else int(current["user_id"])
        if creator_id is not None and not _user_exists(cur, creator_id):
            raise HTTPException(status_code=400, detail="created_by does not reference an existing user")

        cur.execute(
            """
            INSERT INTO workouts
                (name, type, intensity, estimated_minutes, level, created_by)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                payload.name,
                payload.type,
                payload.intensity,
                int(payload.estimated_minutes),
                payload.level,
                creator_id,
            )
        )
        cnx.commit()
        new_id = cur.lastrowid
        row = _fetch_workout_by_id(cur, new_id)
        return _row_to_workout_item(row)
    except mysql_errors.IntegrityError as e:
        cnx.rollback()
        # cover FK fail / CHECK fail / ENUM mismatch (depending on MySQL mode)
        raise HTTPException(status_code=400, detail=f"Integrity error: {e.msg}")
    except Exception as e:
        cnx.rollback()
        raise HTTPException(status_code=500, detail=f"Create failed: {e}")
    finally:
        try:
            cur.close(); cnx.close()
        except Exception:
            pass

@app.get("/api/workouts/{workout_id}", response_model=WorkoutItem)
def get_workout_by_id(workout_id: int):
    try:
        cnx = get_conn(); cur = cnx.cursor(dictionary=True)
        row = _fetch_workout_by_id(cur, workout_id)
        if not row:
            raise HTTPException(status_code=404, detail="Workout not found")
        return _row_to_workout_item(row)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")
    finally:
        try:
            cur.close(); cnx.close()
        except Exception:
            pass

@app.put("/api/workouts/{workout_id}", response_model=WorkoutItem)
def update_workout(workout_id: int, payload: UpdateWorkoutRequest, current=Depends(get_current_user)):
    try:
        cnx = get_conn(); cur = cnx.cursor(dictionary=True)
        row = _fetch_workout_by_id(cur, workout_id)
        if not row:
            raise HTTPException(status_code=404, detail="Workout not found")

        sets = []
        vals: list[Any] = []

        def add(col: str, val):
            sets.append(f"{col}=%s"); vals.append(val)

        if payload.name is not None: add("name", payload.name)
        if payload.type is not None: add("type", payload.type)
        if payload.intensity is not None: add("intensity", payload.intensity)
        if payload.estimated_minutes is not None: add("estimated_minutes", int(payload.estimated_minutes))
        if payload.level is not None: add("level", payload.level)
        if payload.created_by is not None:
            # validate FK
            if not _user_exists(cur, int(payload.created_by)):
                raise HTTPException(status_code=400, detail="created_by does not reference an existing user")
            add("created_by", int(payload.created_by))

        if not sets:
            return _row_to_workout_item(row)

        sql = f"UPDATE workouts SET {', '.join(sets)} WHERE workout_id=%s"
        vals.append(workout_id)
        cur.execute(sql, tuple(vals))
        cnx.commit()

        row2 = _fetch_workout_by_id(cur, workout_id)
        return _row_to_workout_item(row2)
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

@app.delete("/api/workouts/{workout_id}")
def delete_workout(workout_id: int, current=Depends(get_current_user)):
    try:
        cnx = get_conn(); cur = cnx.cursor(dictionary=True)
        cur.execute("DELETE FROM workouts WHERE workout_id=%s", (workout_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Workout not found")
        cnx.commit()
        return {"detail": "Workout deleted successfully."}
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

# ------------------ Dev runner ------------------
if __name__ == "__main__":
    import uvicorn
    # đổi port nếu cần (user.py dùng 8000)
    uvicorn.run("workouts:app", host="0.0.0.0", port=8001, reload=True)
