# TAILOR24 Backend API

Digital on-demand tailoring & garment delivery platform.  
Connects customers, hubs, and independent BYOD tailors under a **24-hour delivery promise**.

---

## Architecture Overview

```
FastAPI Modular Monolith
├── Routers        — HTTP interface, input validation only
├── Services       — All business logic
├── Repositories   — MongoDB access via PyMongo
└── Schemas        — Pydantic v2 request/response models
```

### Critical Design: Append-Only Garment Event Log

**The `garment_events` collection is the authoritative source of truth for garment state.**  
`garment.currentStage` is a **projection/cache** derived from the latest event — it is **never** the source of truth and must **never** be updated independently.

Every workflow transition creates a new, immutable `garment_event` document.  
Events are never edited or deleted through normal application APIs.

---

## Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.12+ (3.14 compatible) |
| MongoDB Atlas | Any current cluster |
| pip | Latest |

---

## Quick Start

### 1. Clone and set up virtual environment

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env with your MongoDB Atlas URI and JWT secret
```

Minimum required variables:
```env
MONGODB_URI=mongodb+srv://<user>:<pass>@<cluster>.mongodb.net/
MONGODB_DATABASE=tailor24
JWT_SECRET=<at-least-64-random-chars>
```

### 4. Initialize the database

```bash
python -m app.scripts.init_db
```

This is **safe to run multiple times** — it will not destroy existing data.

### 5. Seed development data (optional)

```bash
python -m app.scripts.seed_data
```

Creates one of every user role + a sample hub, tailors, customer, and order.  
**Never run in production.**

Seed login: any seed phone (e.g. `+910000000001`) with password `Dev@12345`.

### 6. Start the API

```bash
uvicorn app.main:app --reload
```

API is live at: **http://localhost:8000**  
Swagger docs: **http://localhost:8000/docs**  
Health check: **http://localhost:8000/health**

---

## Running Tests

```bash
# Install mongomock for in-memory testing (optional but recommended)
pip install mongomock

pytest tests/ -v
```

Tests use an in-memory MongoDB (mongomock) or a real `tailor24_test` database.

---

## MongoDB Atlas Setup

1. Create a free M0 cluster at [cloud.mongodb.com](https://cloud.mongodb.com)
2. Create a database user with read/write access
3. Whitelist your IP (or `0.0.0.0/0` for development)
4. Copy the connection string to `MONGODB_URI` in `.env`
5. Run `python -m app.scripts.init_db`

---

## API Modules

| Prefix | Description |
|---|---|
| `POST /api/v1/auth/register` | Register customer or tailor |
| `POST /api/v1/auth/login` | JWT login |
| `GET  /api/v1/auth/me` | Current user profile |
| `POST /api/v1/orders` | Customer creates order |
| `GET  /api/v1/orders/{id}/tracking` | Live garment tracking |
| `POST /api/v1/garments/{id}/scan` | **Advance garment workflow** |
| `GET  /api/v1/garments/{id}/events` | Full event history |
| `GET  /api/v1/garments/{id}/qr-image` | QR code PNG |
| `GET  /api/v1/assignments/garments/{id}/suggest` | Smart tailor suggestions |
| `POST /api/v1/assignments/garments/{id}/assign` | Assign tailor |
| `POST /api/v1/deliveries` | Create delivery |
| `POST /api/v1/deliveries/{id}/confirm` | Confirm with OTP |
| `GET  /api/v1/payouts/ledger/me` | Tailor earnings |
| `POST /api/v1/payouts/claims` | Raise payout claim |
| `PATCH /api/v1/payouts/claims/{id}/manager-review` | Manager approval |
| `PATCH /api/v1/payouts/claims/{id}/finance-confirm` | Finance payment |
| `GET  /api/v1/dashboard` | Live dashboard metrics |
| `GET  /api/v1/tailors` | Tailor list with capacity |
| `PATCH /api/v1/tailors/availability` | Set daily availability |
| `POST /api/v1/tailor-applications` | Submit application |
| `PATCH /api/v1/leave/{id}/review` | Approve/reject leave |
| `GET  /api/v1/hubs` | List hubs |

---

## Project Structure

```
backend/
├── app/
│   ├── main.py                    # FastAPI app, CORS, lifespan
│   ├── core/
│   │   ├── config.py              # Pydantic Settings
│   │   ├── database.py            # PyMongo connection
│   │   ├── security.py            # JWT, bcrypt, OTP
│   │   ├── dependencies.py        # Role guards (FastAPI Depends)
│   │   └── logging_config.py      # Structured logging
│   ├── common/
│   │   ├── enums.py               # All domain enums + VALID_TRANSITIONS
│   │   ├── exceptions.py          # Custom exception hierarchy
│   │   ├── responses.py           # Standard API envelope
│   │   ├── pagination.py          # Pagination helpers
│   │   └── utils.py               # ObjectId/Decimal128 helpers
│   ├── modules/
│   │   ├── auth/                  # Login, register, token refresh
│   │   ├── users/                 # User CRUD
│   │   ├── customers/             # Customer profile
│   │   ├── addresses/             # Customer addresses
│   │   ├── hubs/                  # Hub management
│   │   ├── tailors/               # Profiles, applications, leave
│   │   ├── orders/                # Booking, pricing, tracking
│   │   ├── garments/              # QR, scan API, event log, SLA
│   │   ├── assignments/           # Smart + manual assignment
│   │   ├── deliveries/            # Rider, OTP, COD
│   │   ├── payouts/               # Ledger, two-step claims
│   │   ├── notifications/         # Notification queue
│   │   └── dashboard/             # Live aggregation metrics
│   └── scripts/
│       ├── init_db.py             # Idempotent DB + index setup
│       └── seed_data.py           # Development seed data
├── tests/
│   ├── conftest.py
│   ├── test_auth.py
│   ├── test_garments.py           # Workflow, QR, SLA, event log
│   ├── test_assignments.py        # Scoring, ON_LEAVE, capacity
│   ├── test_payouts.py            # Ledger, claims, two-step
│   ├── test_deliveries.py         # OTP, COD, delivery lifecycle
│   └── test_infrastructure.py    # Health, DB, transitions, QR format
├── .env.example
├── .gitignore
├── requirements.txt
├── Dockerfile
└── README.md
```

---

## Garment Event Workflow

```
INTAKE
  └─► CUTTING_STARTED
        └─► CUTTING_COMPLETED
              └─► STITCHING_ASSIGNED
                    └─► STITCHING_STARTED
                          └─► STITCHING_COMPLETED
                                └─► QC_STARTED
                                      ├─► QC_PASSED
                                      │     └─► IRONING_STARTED
                                      │           └─► IRONING_COMPLETED
                                      │                 └─► PACKED
                                      │                       └─► DISPATCHED
                                      │                             └─► OUT_FOR_DELIVERY
                                      │                                   ├─► DELIVERED  (terminal)
                                      │                                   └─► DELIVERY_FAILED
                                      │                                         └─► OUT_FOR_DELIVERY (retry)
                                      └─► QC_REWORK
                                            └─► STITCHING_STARTED  (rework loop)
```

**Scan API:** `POST /api/v1/garments/{garment_id}/scan`  
```json
{ "action": "CUTTING_STARTED" }
```

There is **no** `PATCH /garments/{id}` endpoint that accepts a raw `status` field.  
All workflow progression goes exclusively through `/scan`.

---

## 24-Hour SLA

- SLA **starts** when the garment is scanned at **INTAKE** — not when the order is created
- `sla.startedAt` = intake event timestamp
- `sla.dueAt` = `startedAt + 24 hours`
- SLA status is computed on-the-fly: `ON_TIME` | `AT_RISK` (< 4h remaining) | `OVERDUE`
- Dashboard shows at-risk garments via MongoDB aggregation (no separate collection)

---

## Smart Assignment Scoring

| Factor | Weight |
|---|---|
| Gender match | +40 |
| Skill / specialization overlap | +25 |
| Capacity headroom (proportional) | +10 |
| Rating | tie-breaker (fractional) |

Weights are configurable via environment variables (`SCORE_WEIGHT_*`).  
`scoreBreakdown` is always returned — the algorithm is transparent.

Rules enforced:
- ON_LEAVE tailors are **never** suggested or assigned
- Assignments beyond `dailyCapacity` are blocked unless `overrideCapacity=true`

---

## Payout Workflow

```
Garment DELIVERED
  └─► payout_ledger entry created (PENDING) — idempotent via unique index on garmentId

Tailor raises payout_claim against PENDING entries
  └─► status: PENDING_MANAGER

Hub Manager reviews
  ├─► approve → MANAGER_APPROVED
  └─► reject  → MANAGER_REJECTED (ledger entries revert to PENDING)

Admin/Finance confirms bank/UPI transfer
  └─► status: FINANCE_PAID (with transferReference)
      └─► all ledger entries → PAID
```

A payout **cannot** become `FINANCE_PAID` without the manager approval step.  
One garment creates **at most one** payout entry (enforced by unique MongoDB index).

---

## Collections

| Collection | Purpose |
|---|---|
| `users` | All user identities and roles |
| `hubs` | Physical workshop locations |
| `addresses` | Customer delivery addresses |
| `tailor_profiles` | Tailor skills, capacity, availability |
| `tailor_applications` | Signup applications |
| `leave_requests` | Tailor leave management |
| `orders` | Customer bookings |
| `garments` | One document per physical garment |
| `garment_events` | **Append-only** workflow event log |
| `tailor_assignments` | Per-assignment records with score |
| `payout_ledger` | Per-garment earnings (unique on garmentId) |
| `payout_claims` | Two-step payout claims |
| `deliveries` | Rider delivery lifecycle |
| `notifications` | Notification queue |

---

## Security

- JWT Bearer tokens (RS256 via `python-jose`)
- Roles enforced from the **database**, never from the token payload
- OTP is hashed (SHA-256 + pepper) before storage — plaintext never persists
- CORS origins set explicitly via environment — no `*` in production
- Secrets only via environment variables — never committed

---

## Remaining External Integrations

These require external credentials and are designed as clean provider interfaces:

| Integration | Status |
|---|---|
| SMS / WhatsApp notifications | Interface ready; plug in Twilio/MSG91 provider |
| Push notifications | Interface ready; plug in FCM/APNs provider |
| Object storage (QR images, PDFs) | S3-compatible; configure `OBJECT_STORAGE_*` env vars |
| UPI / payment gateway | COD tracked; online payment gateway plugin point is `payment.status` |
| PDF signing for tailor applications | `signedPdfKey` field ready; connect a PDF service |

---

## Docker

```bash
docker build -t tailor24-backend .
docker run -p 8000:8000 --env-file .env tailor24-backend
```

---

*Book it. Tag it. Stitch it. Pay it.* 🧵
