# RetailIQ

Sales intelligence dashboard for retail shop owners. Connects to your POS system (Square, Shopify, Clover) and delivers actionable insights on revenue trends, peak hours, customer retention, competitor activity, and Google reviews.

## Quick Start

```bash
cp .env.example .env
docker-compose up --build
```

The app will be available at:
- **Landing page:** http://localhost:8000
- **Dashboard:** http://localhost:8000/dashboard
- **API docs:** http://localhost:8000/docs

## Generate Demo Data

Populate the database with 90 days of realistic mock data:

```bash
docker-compose exec web python -m scripts.generate_mock_data
```

Demo credentials after running the script:
- **Email:** demo@retailiq.com
- **Password:** demo1234

## Run Migrations

```bash
docker-compose exec web alembic upgrade head
```

## Run Tests

```bash
docker-compose exec web pytest tests/ -v
```

## Project Structure

```
retailiq/
├── app/
│   ├── main.py              # FastAPI application entry point
│   ├── config.py             # Settings and environment variables
│   ├── database.py           # SQLAlchemy engine and session
│   ├── dependencies.py       # FastAPI dependencies (auth, db)
│   ├── models.py             # All SQLAlchemy ORM models
│   ├── schemas.py            # Pydantic request/response schemas
│   ├── connectors/           # POS and external API connectors
│   │   ├── base.py           # Abstract base connector
│   │   ├── square.py         # Square POS connector
│   │   ├── shopify.py        # Shopify POS connector
│   │   ├── clover.py         # Clover POS connector
│   │   └── google_places.py  # Google Places API connector
│   ├── services/             # Business logic layer
│   │   ├── auth.py           # Authentication and JWT
│   │   ├── analytics.py      # Analytics engine
│   │   ├── alerts.py         # Alert system
│   │   └── reviews.py        # Review monitoring
│   ├── routers/              # API route handlers
│   │   ├── auth.py           # Auth endpoints
│   │   ├── dashboard_api.py  # Dashboard data API
│   │   └── pages.py          # HTML page routes
│   ├── templates/            # Jinja2 HTML templates
│   └── static/               # CSS, JS, static assets
├── alembic/                  # Database migrations
├── scripts/
│   └── generate_mock_data.py # Demo data generator
├── tests/                    # Unit and integration tests
├── docker-compose.yml
├── Dockerfile
└── .env.example
```

## API Endpoints

### Auth
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/register` | Create account |
| POST | `/api/auth/login` | Login, returns JWT |
| GET | `/api/auth/me` | Current user info |

### Dashboard
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/dashboard/summary` | KPI summary cards |
| GET | `/api/dashboard/sales` | Sales trends and charts |
| GET | `/api/dashboard/products` | Product performance |
| GET | `/api/dashboard/customers` | Customer analytics |
| GET | `/api/dashboard/competitors` | Competitor tracking |
| GET | `/api/dashboard/reviews` | Google review feed |
| GET | `/api/dashboard/alerts` | Active alerts |

## Tech Stack

- **Backend:** Python, FastAPI, SQLAlchemy, Alembic
- **Database:** PostgreSQL
- **Cache:** Redis
- **Frontend:** Jinja2, Chart.js, vanilla JS
- **Deployment:** Docker, docker-compose
