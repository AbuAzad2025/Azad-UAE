# Deployment Guide — Azadexa ERP

## 1. Infrastructure Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| Application server | 2 vCPU, 4 GB RAM | 4 vCPU, 8 GB RAM |
| Database server | 2 vCPU, 4 GB RAM, SSD | 4 vCPU, 16 GB RAM, NVMe SSD |
| Redis server | 1 vCPU, 2 GB RAM | 2 vCPU, 4 GB RAM |
| Storage | 50 GB | 200 GB |
| Network | 100 Mbps | 1 Gbps |
| OS | Ubuntu 22.04 LTS | Ubuntu 24.04 LTS |

## 2. Software Prerequisites

| Software | Version | Installation |
|----------|---------|--------------|
| Python | 3.11 | `apt install python3.11 python3.11-venv` |
| PostgreSQL | 15 | `apt install postgresql-15` |
| Redis | 7+ | `apt install redis-server` |
| Nginx | 1.24+ | `apt install nginx` |
| Node.js | 18+ | For asset building only |

## 3. Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | Yes | Flask secret key (64+ random chars) |
| `SQLALCHEMY_DATABASE_URI` | Yes | PostgreSQL connection string |
| `CELERY_BROKER_URL` | Yes | Redis URL for Celery |
| `CELERY_RESULT_BACKEND` | Yes | Redis URL for results |
| `CARD_ENCRYPTION_KEY` | Yes | 32-byte base64 key for card vault |
| `OWNER_PASSWORD` | Yes | Owner panel password (hashed) |
| `MAIL_SERVER` | No | SMTP server for transactional email |
| `MAIL_USERNAME` | No | SMTP username |
| `MAIL_PASSWORD` | No | SMTP password |
| `GOOGLE_SITE_VERIFICATION` | No | Google Search Console token |
| `SENTRY_DSN` | No | Error tracking (roadmap) |

## 4. Installation Steps

### 4.1 Clone and Setup

```bash
git clone https://github.com/AbuAzad2025/Azad-UAE.git
cd Azad-UAE
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4.2 Database

```bash
sudo -u postgres createdb azadexa
flask db upgrade
```

### 4.3 Redis

```bash
sudo systemctl enable redis
sudo systemctl start redis
```

### 4.4 Assets

```bash
flask build-assets
```

### 4.5 First Run

```bash
export FLASK_APP=app.py
flask run --host=0.0.0.0 --port=5000
```

## 5. Production Configuration

### 5.1 Gunicorn

```bash
gunicorn -w 4 -b 127.0.0.1:5000 wsgi:app
```

### 5.2 Nginx

```nginx
server {
    listen 80;
    server_name azadsystems.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name azadsystems.com;

    ssl_certificate /etc/letsencrypt/live/azadsystems.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/azadsystems.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /var/www/azadexa/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

### 5.3 Celery

```bash
celery -A app.celery worker --loglevel=info --concurrency=4
celery -A app.celery beat --loglevel=info
```

Use `systemd` services for auto-start.

### 5.4 SSL/TLS

- Let's Encrypt for TLS 1.3.
- Auto-renewal via `certbot renew`.
- HSTS header enabled.

## 6. Docker (Optional)

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "wsgi:app"]
```

```yaml
version: '3.8'
services:
  app:
    build: .
    ports:
      - "5000:5000"
    environment:
      - SQLALCHEMY_DATABASE_URI=postgresql+psycopg2://postgres:pass@db:5432/azadexa
    depends_on:
      - db
      - redis
  db:
    image: postgres:15
    environment:
      POSTGRES_DB: azadexa
  redis:
    image: redis:7
  worker:
    build: .
    command: celery -A app.celery worker --loglevel=info
    depends_on:
      - redis
      - db
```

## 7. Monitoring

| Tool | Purpose | Status |
|------|---------|--------|
| `routes/owner/monitoring.py` | Built-in health dashboard | Active |
| Prometheus + Grafana | Metrics and dashboards | Roadmap Q4 2026 |
| Sentry | Error tracking | Roadmap Q4 2026 |
| UptimeRobot | External uptime monitoring | Recommended |

## 8. Scaling

| Scale Type | Trigger | Action |
|------------|---------|--------|
| Vertical | CPU > 80% for 5 min | Increase instance size |
| Horizontal | Requests > 500/sec | Add Gunicorn workers or load balancer |
| Database | Connections > 80% | Connection pooling (PgBouncer) |
| Cache | Hit rate < 70% | Increase Redis memory or shard |

## 9. Backup and Recovery

| Backup | Frequency | Command |
|--------|-----------|---------|
| Full DB | Daily | `pg_dump azadexa | gzip > backup.sql.gz` |
| WAL archive | Continuous | PostgreSQL archive_mode |
| Scoped export | Weekly | `flask backup` |

Recovery RPO: 24 hours. RTO: 4 hours.

## 10. Support

DevOps support: devops@azadsystems.com
Emergency: +972 56 215 0193
