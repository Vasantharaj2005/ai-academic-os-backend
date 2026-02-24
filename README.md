# 🎓 AI Academic Operating System — Backend

A production-grade FastAPI multi-agent AI platform that autonomously generates complete academic course packages using 6 specialized AI agents.

---

## 🏗️ Architecture

```
CLIENT (React/Mobile)
        │
        ▼
API GATEWAY (FastAPI)
├── Auth Routes          ─► JWT authentication
├── Course APIs          ─► CRUD operations
├── Generation APIs      ─► Triggers AI pipeline
├── Assessment APIs      ─► Question banks
├── Compliance APIs      ─► OBE/NBA reports
└── Analytics APIs       ─► Performance insights
        │
        ▼
AGENT ORCHESTRATOR
├── Phase 1: CurriculumAgent   ─► Syllabus + CLOs
├── Phase 2: SemesterAgent  ┐  ─► 16-week plan
│           ContentAgent    ┘  ─► Lecture content (parallel)
├── Phase 3: AssessmentAgent   ─► Exams + QBank
├── Phase 4: OBEAgent          ─► CO-PO mapping
└── Phase 5: AnalyticsAgent    ─► Predictions
        │
        ▼
AI SERVICE LAYER
├── OpenAI GPT-4 (primary)
├── Anthropic Claude (fallback)
├── RAG via Pinecone
└── Bloom's Classifier
        │
        ▼
DATA LAYER
├── PostgreSQL  ─► Primary database
├── Redis       ─► Shared memory + rate limiting
├── Pinecone    ─► Vector DB for RAG
└── AWS S3      ─► File storage
```

---

## 🚀 Quick Start

### 1. Clone & Configure

```bash
git clone <repo-url>
cd ai-academic-os-backend
cp .env.example .env
# Edit .env with your API keys and database credentials
```

### 2. Run with Docker Compose (Recommended)

```bash
docker-compose up -d
```

Services started:
- **API**: http://localhost:8000
- **API Docs**: http://localhost:8000/api/docs
- **Flower** (Celery): http://localhost:5555
- **Grafana**: http://localhost:3001

### 3. Run Locally (Development)

```bash
# Install dependencies
pip install -r requirements.txt

# Initialize database
python scripts/init_db.py

# Start API
uvicorn app.main:app --reload --port 8000

# Start Celery worker (separate terminal)
celery -A app.workers.celery_app worker --loglevel=info
```

---

## 🔑 API Usage

### Authentication

```bash
# Register
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"prof@college.edu","username":"prof","password":"Prof@12345","full_name":"Dr. Smith","role":"faculty"}'

# Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"prof@college.edu","password":"Prof@12345"}'
# → Returns: access_token, refresh_token
```

### Generate a Course

```bash
# 1. Create course
curl -X POST http://localhost:8000/api/v1/courses \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Data Structures and Algorithms",
    "program": "B.Tech",
    "department": "Computer Science",
    "semester": 3,
    "credits": 4
  }'
# → Returns: course_id

# 2. Start generation
curl -X POST http://localhost:8000/api/v1/courses/<course_id>/generate \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"course_id": "<course_id>", "mode": "full"}'
# → Returns: workflow_id

# 3. Check status
curl http://localhost:8000/api/v1/courses/<course_id>/status \
  -H "Authorization: Bearer <token>"

# 4. Get result (when completed)
curl http://localhost:8000/api/v1/courses/<course_id>/result \
  -H "Authorization: Bearer <token>"
```

---

## 🤖 Agent Pipeline

| Agent | Input | Output | Time |
|-------|-------|--------|------|
| **CurriculumAgent** | Course details | Syllabus, CLOs, modules | ~20s |
| **SemesterAgent** | Curriculum | 16-week teaching plan | ~15s |
| **ContentAgent** | Curriculum | Lecture notes, slide outlines | ~45s |
| **AssessmentAgent** | Curriculum + Semester plan | Exams, question bank | ~40s |
| **OBEAgent** | Curriculum + Assessments | CO-PO mapping, NBA report | ~20s |
| **AnalyticsAgent** | All outputs | Performance predictions | ~15s |

Total generation time: **~3-8 minutes** depending on LLM response times.

---

## 📁 Project Structure

```
app/
├── main.py              ← FastAPI app entry point
├── config.py            ← Settings (pydantic-settings)
├── api/routes/          ← HTTP endpoints
├── agents/              ← 6 specialized AI agents
├── core/
│   ├── orchestrator.py  ← Master workflow coordinator
│   └── memory.py        ← Redis shared memory
├── services/
│   ├── ai/              ← LLM, RAG, Bloom classifier
│   ├── database/        ← SQLAlchemy session
│   └── storage/         ← S3 file storage
├── models/
│   ├── database/        ← SQLAlchemy ORM models
│   └── schemas/         ← Pydantic request/response schemas
├── workers/             ← Celery tasks
├── middleware/          ← Auth, rate limiting, request ID
└── utils/               ← Helpers, exceptions, metrics
```

---

## 🧪 Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific module
pytest tests/unit/test_agents/ -v
```

---

## 📊 Monitoring

- **Metrics**: Prometheus at http://localhost:9090
- **Dashboard**: Grafana at http://localhost:3001 (admin/admin123)
- **Task Monitor**: Flower at http://localhost:5555
- **Logs**: `./logs/app.log`

---

## ⚙️ Configuration Reference

| Variable | Description | Required |
|----------|-------------|----------|
| `OPENAI_API_KEY` | OpenAI API key | Yes (or Anthropic) |
| `ANTHROPIC_API_KEY` | Claude API key | No (fallback) |
| `PINECONE_API_KEY` | Pinecone vector DB | No (RAG disabled) |
| `POSTGRES_PASSWORD` | Database password | Yes |
| `SECRET_KEY` | JWT secret (32+ chars) | Yes |
| `AWS_ACCESS_KEY_ID` | S3 file storage | No |

---

## 🔒 Security

- JWT authentication with refresh token rotation
- Bcrypt password hashing (12 rounds)
- Redis-based rate limiting (1000 req/min)
- Role-based access control (Admin, HOD, Faculty, Student)
- CORS configuration
- Request ID tracking

---

## 📦 Tech Stack

- **FastAPI** 0.104 + **Uvicorn** (ASGI)
- **SQLAlchemy** 2.0 async + **Alembic** migrations
- **PostgreSQL** 15 + **Redis** 7
- **Celery** 5.3 (background tasks)
- **OpenAI** GPT-4 / **Anthropic** Claude
- **Pinecone** (vector search / RAG)
- **Prometheus** + **Grafana** (monitoring)
- **Docker** + **Docker Compose**