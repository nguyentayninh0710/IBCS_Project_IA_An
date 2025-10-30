# exercises.py — Fitness Exercises API + Workout Exercises (JOIN) (CRUD + JWT-guarded writes)
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Literal, Dict, Any, Tuple

from dotenv import load_dotenv
import mysql.connector
from mysql.connector import errors as mysql_errors
from fastapi import FastAPI, HTTPException, Depends, status, Request, Query
from fastapi.security import OAuth2PasswordBearer
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from starlette.middleware.base import BaseHTTPMiddleware
import jwt  # PyJWT

print("Now UTC:", datetime.now(timezone.utc).isoformat())

# ================== ENV & CONSTANTS ==================
load_dotenv()
DB_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("MYSQL_PORT", "3306"))
DB_USER = os.getenv("MYSQL_USER", "root")
DB_PASS = os.getenv("MYSQL_PASSWORD", "")
DB_NAME = os.getenv("MYSQL_DB", "fitness_app_sl")

JWT_SECRET = os.getenv("JWT_SECRET", "change_me_super_secret")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_MINUTES", "60"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_DAYS", "7"))

CATEGORIES = ("cardio", "strength", "mobility")
UNITS = ("reps", "seconds")
DIFFICULTIES = ("beginner", "intermediate")
BODY_AREAS = ("full_body", "upper", "lower", "core")

# ================== APP & CORS ==================
app = FastAPI(title="Exercises API (Fitness)", version="1.0")

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

class LogHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # print("[DEBUG] Incoming Request Headers:", dict(request.headers))
        return await call_next(request)

app.add_middleware(LogHeadersMiddleware)

# ================== DB HELPERS ==================
def get_conn():
    return mysql.connector.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS, database=DB_NAME
    )

def table_exists(cur, table_name: str) -> bool:
    cur.execute("SHOW TABLES LIKE %s", (table_name,))
    return cur.fetchone() is not None

# ================== JWT HELPERS ==================
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
REVOKED_JTI: set[str] = set()

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)

def _epoch(dt: datetime) -> int:
    return int(dt.timestamp())

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM], leeway=60)
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

    # verify user still exists
    try:
        cnx = get_conn(); cur = cnx.cursor(dictionary=True)
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

# ================== Pydantic MODELS ==================
class ExerciseBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    category: Literal["cardio", "strength", "mobility"]
    unit: Literal["reps", "seconds"]
    difficulty: Literal["beginner", "intermediate"] = "beginner"
    body_area: Literal["full_body", "upper", "lower", "core"] = "full_body"
    video_url: Optional[str] = Field(None, max_length=500)
    description: Optional[str] = None

    @validator("name")
    def _trim_name(cls, v):
        return v.strip()

class ExerciseItem(ExerciseBase):
    exercise_id: int

class CreateExerciseRequest(ExerciseBase):
    pass

class UpdateExerciseRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=120)
    category: Optional[Literal["cardio", "strength", "mobility"]] = None
    unit: Optional[Literal["reps", "seconds"]] = None
    difficulty: Optional[Literal["beginner", "intermediate"]] = None
    body_area: Optional[Literal["full_body", "upper", "lower", "core"]] = None
    video_url: Optional[str] = Field(None, max_length=500)
    description: Optional[str] = None

    @validator("name")
    def _trim_name(cls, v):
        return v.strip() if v is not None else v

class WorkoutExerciseBase(BaseModel):
    exercise_id: int
    seq_no: int = Field(..., ge=1)
    target_reps: Optional[int] = Field(None, ge=1, le=200)
    target_seconds: Optional[int] = Field(None, ge=5, le=600)
    rest_seconds: Optional[int] = Field(None, ge=0, le=300)

class WorkoutExerciseCreate(WorkoutExerciseBase):
    pass

class WorkoutExerciseUpdate(BaseModel):
    # cho phép đổi exercise_id hoặc seq_no
    exercise_id: Optional[int] = None
    seq_no: Optional[int] = Field(None, ge=1)
    target_reps: Optional[int] = Field(None, ge=1, le=200)
    target_seconds: Optional[int] = Field(None, ge=5, le=600)
    rest_seconds: Optional[int] = Field(None, ge=0, le=300)

class WorkoutExerciseView(WorkoutExerciseBase):
    # VIEW model khi JOIN cùng exercises
    workout_id: int
    name: str
    category: Literal["cardio", "strength", "mobility"]
    unit: Literal["reps", "seconds"]
    difficulty: Literal["beginner", "intermediate"]
    body_area: Literal["full_body", "upper", "lower", "core"]
    video_url: Optional[str] = None
    description: Optional[str] = None

# ================== ROW MAPPERS ==================
def _row_to_exercise(row: dict) -> ExerciseItem:
    return ExerciseItem(
        exercise_id=row["exercise_id"],
        name=row["name"],
        category=row["category"],
        unit=row["unit"],
        difficulty=row["difficulty"],
        body_area=row["body_area"],
        video_url=row.get("video_url"),
        description=row.get("description"),
    )

def _row_to_we_view(row: dict) -> WorkoutExerciseView:
    return WorkoutExerciseView(
        workout_id=row["workout_id"],
        exercise_id=row["exercise_id"],
        seq_no=row["seq_no"],
        target_reps=row.get("target_reps"),
        target_seconds=row.get("target_seconds"),
        rest_seconds=row.get("rest_seconds"),
        name=row["name"],
        category=row["category"],
        unit=row["unit"],
        difficulty=row["difficulty"],
        body_area=row["body_area"],
        video_url=row.get("video_url"),
        description=row.get("description"),
    )

# ================== INTERNAL HELPERS ==================
def _exercise_exists(cur, exercise_id: int) -> bool:
    cur.execute("SELECT 1 FROM exercises WHERE exercise_id=%s LIMIT 1", (exercise_id,))
    return cur.fetchone() is not None

def _workout_exists(cur, workout_id: int) -> bool:
    cur.execute("SELECT 1 FROM workouts WHERE workout_id=%s LIMIT 1", (workout_id,))
    return cur.fetchone() is not None

def _we_row_by_seq(cur, workout_id: int, seq_no: int) -> Optional[dict]:
    cur.execute(
        """
        SELECT workout_id, exercise_id, seq_no, target_reps, target_seconds, rest_seconds
        FROM workout_exercises
        WHERE workout_id=%s AND seq_no=%s
        LIMIT 1
        """,
        (workout_id, seq_no),
    )
    return cur.fetchone()

# ================== EXERCISES CRUD ==================
@app.get("/api/exercises", response_model=List[ExerciseItem])
def list_exercises(
    q: Optional[str] = Query(None, description="search by name (contains)"),
    category: Optional[Literal["cardio", "strength", "mobility"]] = Query(None),
    unit: Optional[Literal["reps", "seconds"]] = Query(None),
    difficulty: Optional[Literal["beginner", "intermediate"]] = Query(None),
    body_area: Optional[Literal["full_body", "upper", "lower", "core"]] = Query(None),
):
    try:
        cnx = get_conn(); cur = cnx.cursor(dictionary=True)
        if not table_exists(cur, "exercises"):
            raise HTTPException(status_code=500, detail="Table `exercises` not found")

        clauses = []
        vals: list[Any] = []

        if q:
            clauses.append("name LIKE %s"); vals.append(f"%{q.strip()}%")
        if category:
            clauses.append("category=%s"); vals.append(category)
        if unit:
            clauses.append("unit=%s"); vals.append(unit)
        if difficulty:
            clauses.append("difficulty=%s"); vals.append(difficulty)
        if body_area:
            clauses.append("body_area=%s"); vals.append(body_area)

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        cur.execute(
            f"""
            SELECT exercise_id, name, category, unit, difficulty, body_area, video_url, description
            FROM exercises
            {where_sql}
            ORDER BY exercise_id ASC
            """,
            tuple(vals)
        )
        rows = cur.fetchall() or []
        return [_row_to_exercise(r) for r in rows]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")
    finally:
        try:
            cur.close(); cnx.close()
        except Exception:
            pass

@app.get("/api/exercises/{exercise_id}", response_model=ExerciseItem)
def get_exercise(exercise_id: int):
    try:
        cnx = get_conn(); cur = cnx.cursor(dictionary=True)
        cur.execute(
            """
            SELECT exercise_id, name, category, unit, difficulty, body_area, video_url, description
            FROM exercises WHERE exercise_id=%s LIMIT 1
            """,
            (exercise_id,)
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Exercise not found")
        return _row_to_exercise(row)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")
    finally:
        try:
            cur.close(); cnx.close()
        except Exception:
            pass

@app.post("/api/exercises", response_model=ExerciseItem, status_code=201)
def create_exercise(payload: CreateExerciseRequest, current=Depends(get_current_user)):
    try:
        cnx = get_conn(); cur = cnx.cursor(dictionary=True)
        cur.execute(
            """
            INSERT INTO exercises
                (name, category, unit, difficulty, body_area, video_url, description)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                payload.name, payload.category, payload.unit,
                payload.difficulty, payload.body_area,
                payload.video_url, payload.description
            )
        )
        cnx.commit()
        new_id = cur.lastrowid
        cur.execute(
            """
            SELECT exercise_id, name, category, unit, difficulty, body_area, video_url, description
            FROM exercises WHERE exercise_id=%s
            """,
            (new_id,)
        )
        row = cur.fetchone()
        return _row_to_exercise(row)
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

@app.put("/api/exercises/{exercise_id}", response_model=ExerciseItem)
def update_exercise(exercise_id: int, payload: UpdateExerciseRequest, current=Depends(get_current_user)):
    try:
        cnx = get_conn(); cur = cnx.cursor(dictionary=True)
        cur.execute("SELECT * FROM exercises WHERE exercise_id=%s LIMIT 1", (exercise_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Exercise not found")

        sets = []
        vals: list[Any] = []
        def add(col, val): sets.append(f"{col}=%s"); vals.append(val)

        if payload.name is not None: add("name", payload.name)
        if payload.category is not None: add("category", payload.category)
        if payload.unit is not None: add("unit", payload.unit)
        if payload.difficulty is not None: add("difficulty", payload.difficulty)
        if payload.body_area is not None: add("body_area", payload.body_area)
        if payload.video_url is not None: add("video_url", payload.video_url)
        if payload.description is not None: add("description", payload.description)

        if not sets:
            # nothing to update
            cur.execute(
                """
                SELECT exercise_id, name, category, unit, difficulty, body_area, video_url, description
                FROM exercises WHERE exercise_id=%s
                """, (exercise_id,)
            )
            return _row_to_exercise(cur.fetchone())

        sql = f"UPDATE exercises SET {', '.join(sets)} WHERE exercise_id=%s"
        vals.append(exercise_id)
        cur.execute(sql, tuple(vals))
        cnx.commit()
        cur.execute(
            """
            SELECT exercise_id, name, category, unit, difficulty, body_area, video_url, description
            FROM exercises WHERE exercise_id=%s
            """, (exercise_id,)
        )
        return _row_to_exercise(cur.fetchone())
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

@app.delete("/api/exercises/{exercise_id}")
def delete_exercise(exercise_id: int, current=Depends(get_current_user)):
    try:
        cnx = get_conn(); cur = cnx.cursor()
        cur.execute("DELETE FROM exercises WHERE exercise_id=%s", (exercise_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Exercise not found")
        cnx.commit()
        return {"detail": "Exercise deleted successfully."}
    except HTTPException:
        raise
    except mysql_errors.IntegrityError as e:
        # bị RESTRICT do exercise đang được dùng trong workout_exercises
        cnx.rollback()
        raise HTTPException(status_code=409, detail=f"Cannot delete: exercise in use. {e.msg}")
    except Exception as e:
        cnx.rollback()
        raise HTTPException(status_code=500, detail=f"Delete failed: {e}")
    finally:
        try:
            cur.close(); cnx.close()
        except Exception:
            pass

# ================== WORKOUT_EXERCISES (JOIN) ==================
@app.get("/api/workouts/{workout_id}/exercises", response_model=List[WorkoutExerciseView])
def list_exercises_by_workout(workout_id: int):
    """
    Trả về danh sách exercises của workout (theo seq_no ASC),
    bao gồm thông tin bài tập + targets + rest_seconds.
    """
    try:
        cnx = get_conn(); cur = cnx.cursor(dictionary=True)
        if not table_exists(cur, "workouts") or not table_exists(cur, "workout_exercises") or not table_exists(cur, "exercises"):
            raise HTTPException(status_code=500, detail="Required tables not found")

        if not _workout_exists(cur, workout_id):
            raise HTTPException(status_code=404, detail="Workout not found")

        cur.execute(
            """
            SELECT
              we.workout_id,
              we.exercise_id,
              we.seq_no,
              we.target_reps,
              we.target_seconds,
              we.rest_seconds,
              e.name,
              e.category,
              e.unit,
              e.difficulty,
              e.body_area,
              e.video_url,
              e.description
            FROM workout_exercises we
            JOIN exercises e ON e.exercise_id = we.exercise_id
            WHERE we.workout_id = %s
            ORDER BY we.seq_no ASC
            """,
            (workout_id,)
        )
        rows = cur.fetchall() or []
        return [_row_to_we_view(r) for r in rows]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")
    finally:
        try:
            cur.close(); cnx.close()
        except Exception:
            pass

@app.post("/api/workouts/{workout_id}/exercises", response_model=WorkoutExerciseView, status_code=201)
def attach_exercise_to_workout(workout_id: int, payload: WorkoutExerciseCreate, current=Depends(get_current_user)):
    """
    Gán một exercise vào workout với seq_no + targets.
    Lưu ý: UNIQUE (workout_id, exercise_id) & PK (workout_id, seq_no)
    """
    try:
        cnx = get_conn(); cur = cnx.cursor(dictionary=True)
        if not _workout_exists(cur, workout_id):
            raise HTTPException(status_code=404, detail="Workout not found")
        if not _exercise_exists(cur, payload.exercise_id):
            raise HTTPException(status_code=400, detail="Exercise not found")

        cur.execute(
            """
            INSERT INTO workout_exercises
                (workout_id, exercise_id, seq_no, target_reps, target_seconds, rest_seconds)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                workout_id,
                int(payload.exercise_id),
                int(payload.seq_no),
                payload.target_reps,
                payload.target_seconds,
                payload.rest_seconds,
            )
        )
        cnx.commit()
        # fetch view
        cur.execute(
            """
            SELECT
              we.workout_id, we.exercise_id, we.seq_no, we.target_reps, we.target_seconds, we.rest_seconds,
              e.name, e.category, e.unit, e.difficulty, e.body_area, e.video_url, e.description
            FROM workout_exercises we
            JOIN exercises e ON e.exercise_id = we.exercise_id
            WHERE we.workout_id=%s AND we.seq_no=%s
            """,
            (workout_id, payload.seq_no)
        )
        row = cur.fetchone()
        return _row_to_we_view(row)
    except mysql_errors.IntegrityError as e:
        cnx.rollback()
        # có thể va vào PK trùng seq_no hoặc UNIQUE uq_we (workout_id, exercise_id)
        raise HTTPException(status_code=400, detail=f"Integrity error: {e.msg}")
    except Exception as e:
        cnx.rollback()
        raise HTTPException(status_code=500, detail=f"Attach failed: {e}")
    finally:
        try:
            cur.close(); cnx.close()
        except Exception:
            pass

@app.put("/api/workouts/{workout_id}/exercises/{seq_no}", response_model=WorkoutExerciseView)
def update_workout_exercise(workout_id: int, seq_no: int, payload: WorkoutExerciseUpdate, current=Depends(get_current_user)):
    """
    Cập nhật 1 dòng junction theo (workout_id, seq_no).
    Có thể đổi exercise_id hoặc đổi seq_no (nếu muốn reorder).
    """
    try:
        cnx = get_conn(); cur = cnx.cursor(dictionary=True)
        row = _we_row_by_seq(cur, workout_id, seq_no)
        if not row:
            raise HTTPException(status_code=404, detail="Workout-exercise not found")

        sets = []
        vals: list[Any] = []
        def add(col, val): sets.append(f"{col}=%s"); vals.append(val)

        if payload.exercise_id is not None:
            if not _exercise_exists(cur, int(payload.exercise_id)):
                raise HTTPException(status_code=400, detail="Exercise not found")
            add("exercise_id", int(payload.exercise_id))
        if payload.seq_no is not None:
            add("seq_no", int(payload.seq_no))
        if payload.target_reps is not None:
            add("target_reps", int(payload.target_reps))
        if payload.target_seconds is not None:
            add("target_seconds", int(payload.target_seconds))
        if payload.rest_seconds is not None:
            add("rest_seconds", int(payload.rest_seconds))

        if not sets:
            # nothing to update, return current view
            cur.execute(
                """
                SELECT
                  we.workout_id, we.exercise_id, we.seq_no, we.target_reps, we.target_seconds, we.rest_seconds,
                  e.name, e.category, e.unit, e.difficulty, e.body_area, e.video_url, e.description
                FROM workout_exercises we
                JOIN exercises e ON e.exercise_id = we.exercise_id
                WHERE we.workout_id=%s AND we.seq_no=%s
                """,
                (workout_id, seq_no)
            )
            return _row_to_we_view(cur.fetchone())

        sql = f"UPDATE workout_exercises SET {', '.join(sets)} WHERE workout_id=%s AND seq_no=%s"
        vals.append(workout_id); vals.append(seq_no)
        cur.execute(sql, tuple(vals))
        cnx.commit()

        # If seq_no changed, use new seq_no to fetch; else old.
        new_seq = payload.seq_no if payload.seq_no is not None else seq_no
        cur.execute(
            """
            SELECT
              we.workout_id, we.exercise_id, we.seq_no, we.target_reps, we.target_seconds, we.rest_seconds,
              e.name, e.category, e.unit, e.difficulty, e.body_area, e.video_url, e.description
            FROM workout_exercises we
            JOIN exercises e ON e.exercise_id = we.exercise_id
            WHERE we.workout_id=%s AND we.seq_no=%s
            """,
            (workout_id, new_seq)
        )
        row2 = cur.fetchone()
        if not row2:
            # trường hợp đổi seq_no đè vào PK khác gây chuyển vị, refetch toàn bộ để tìm theo exercise_id
            cur.execute(
                """
                SELECT
                  we.workout_id, we.exercise_id, we.seq_no, we.target_reps, we.target_seconds, we.rest_seconds,
                  e.name, e.category, e.unit, e.difficulty, e.body_area, e.video_url, e.description
                FROM workout_exercises we
                JOIN exercises e ON e.exercise_id = we.exercise_id
                WHERE we.workout_id=%s AND we.exercise_id=%s
                """,
                (workout_id, payload.exercise_id if payload.exercise_id is not None else row["exercise_id"])
            )
            row2 = cur.fetchone()
        return _row_to_we_view(row2)
    except mysql_errors.IntegrityError as e:
        cnx.rollback()
        # có thể đụng PK (workout_id, seq_no) hoặc UNIQUE uq_we (workout_id, exercise_id)
        raise HTTPException(status_code=400, detail=f"Integrity error: {e.msg}")
    except Exception as e:
        cnx.rollback()
        raise HTTPException(status_code=500, detail=f"Update failed: {e}")
    finally:
        try:
            cur.close(); cnx.close()
        except Exception:
            pass

@app.delete("/api/workouts/{workout_id}/exercises/{seq_no}")
def detach_exercise_from_workout(workout_id: int, seq_no: int, current=Depends(get_current_user)):
    try:
        cnx = get_conn(); cur = cnx.cursor()
        cur.execute(
            "DELETE FROM workout_exercises WHERE workout_id=%s AND seq_no=%s",
            (workout_id, seq_no)
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Workout-exercise not found")
        cnx.commit()
        return {"detail": "Detached successfully."}
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

# ================== DEV RUNNER ==================
if __name__ == "__main__":
    import uvicorn
    # chạy port 8002 để tránh đụng workouts.py (8001)
    uvicorn.run("exercises:app", host="0.0.0.0", port=8002, reload=True)
