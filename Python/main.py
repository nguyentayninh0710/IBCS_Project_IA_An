# main.py — Unified FastAPI for Users + Workouts + Exercises

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import các module hiện có (chỉ lấy router từ mỗi app con)
from user import app as user_app
from workouts import app as workouts_app
from exercises import app as exercises_app

# Tạo app chính
app = FastAPI(
    title="Fitness Suite APIs",
    version="1.0",
    description="Unified server for Users, Workouts, and Exercises"
)

# CORS
ALLOWED_ORIGINS = [
    "http://127.0.0.1:5500", "http://localhost:5500",
    "http://127.0.0.1:5501", "http://localhost:5501",
    "http://127.0.0.1:5502", "http://localhost:5502",
    "http://127.0.0.1:5503", "http://localhost:5503",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Gắn toàn bộ routes từ 3 app con (giữ nguyên path /api/... của từng file)
app.include_router(user_app.router)
app.include_router(workouts_app.router)
app.include_router(exercises_app.router)

# Health check gọn nhẹ
@app.get("/api/health")
def health():
    return {"status": "ok"}

# Dev runner
if __name__ == "__main__":
    import uvicorn
    # Chọn 1 cổng duy nhất cho tất cả API; 8001 thường hợp với frontend hiện tại
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
