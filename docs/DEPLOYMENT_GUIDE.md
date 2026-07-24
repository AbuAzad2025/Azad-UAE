# Deployment Guide | دليل النشر

## 1. Infrastructure Requirements | متطلبات البنية التحتية

| Component (EN) | المكوّن (AR) | Minimum | الحد الأدنى | Recommended | الموصى به |
|-----------------|-------------|---------|------------|-------------|-----------|
| Application server | خادم التطبيق | 2 vCPU, 4 GB RAM | 2 vCPU، 4 جيجابايت رام | 4 vCPU, 8 GB RAM | 4 vCPU، 8 جيجابايت رام |
| Database server | خادم قاعدة البيانات | 2 vCPU, 4 GB RAM, SSD | 2 vCPU، 4 جيجابايت رام، SSD | 4 vCPU, 16 GB RAM, NVMe SSD | 4 vCPU، 16 جيجابايت رام، NVMe SSD |
| Redis server | خادم Redis | 1 vCPU, 2 GB RAM | 1 vCPU، 2 جيجابايت رام | 2 vCPU, 4 GB RAM | 2 vCPU، 4 جيجابايت رام |
| Storage | التخزين | 50 GB | 50 جيجابايت | 200 GB | 200 جيجابايت |
| Network | الشبكة | 100 Mbps | 100 ميغابت/ثانية | 1 Gbps | 1 جيجابت/ثانية |
| OS | نظام التشغيل | Ubuntu 22.04 LTS | Ubuntu 22.04 LTS | Ubuntu 24.04 LTS | Ubuntu 24.04 LTS |

## 2. Software Prerequisites | المتطلبات البرمجية

| Software (EN) | البرمجية | Version | الإصدار | Installation | التثبيت |
|---------------|----------|---------|---------|--------------|---------|
| Python | بايثون | 3.11 | 3.11 | `apt install python3.11 python3.11-venv` | `apt install python3.11 python3.11-venv` |
| PostgreSQL | PostgreSQL | 15 | 15 | `apt install postgresql-15` | `apt install postgresql-15` |
| Redis | Redis | 7+ | 7+ | `apt install redis-server` | `apt install redis-server` |
| Nginx | Nginx | 1.24+ | 1.24+ | `apt install nginx` | `apt install nginx` |
| Node.js | Node.js | 18+ | 18+ | For asset building only | لبناء الأصول فقط |

## 3. Environment Variables | متغيرات البيئة

| Variable (EN) | المتغير | Required | مطلوب | Description | الوصف |
|---------------|---------|----------|-------|-------------|-------|
| `SECRET_KEY` | `SECRET_KEY` | Yes | نعم | Flask secret key (64+ random chars) | مفتاح سر Flask (64+ حرف عشوائي) |
| `SQLALCHEMY_DATABASE_URI` | `SQLALCHEMY_DATABASE_URI` | Yes | نعم | PostgreSQL connection string | سلسلة الاتصال PostgreSQL |
| `CELERY_BROKER_URL` | `CELERY_BROKER_URL` | Yes | نعم | Redis URL for Celery | URL Redis لـ Celery |
| `CELERY_RESULT_BACKEND` | `CELERY_RESULT_BACKEND` | Yes | نعم | Redis URL for results | URL Redis للنتائج |
| `CARD_ENCRYPTION_KEY` | `CARD_ENCRYPTION_KEY` | Yes | نعم | 32-byte base64 key for card vault | مفتاح base64 32 بايت لخزينة البطاقة |
| `OWNER_PASSWORD` | `OWNER_PASSWORD` | Yes | نعم | Owner panel password (hashed) | كلمة مرور لوحة المالك (مُجزأة) |
| `MAIL_SERVER` | `MAIL_SERVER` | No | لا | SMTP server for transactional email | خادم SMTP للبريد المعاملاتي |
| `MAIL_USERNAME` | `MAIL_USERNAME` | No | لا | SMTP username | اسم مستخدم SMTP |
| `MAIL_PASSWORD` | `MAIL_PASSWORD` | No | لا | SMTP password | كلمة مرور SMTP |
| `GOOGLE_SITE_VERIFICATION` | `GOOGLE_SITE_VERIFICATION` | No | لا | Google Search Console token | رمز Google Search Console |
| `SENTRY_DSN` | `SENTRY_DSN` | No | لا | Error tracking (roadmap) | تتبع الأخطاء (خارطة الطريق) |

## 4. Installation Steps | خطوات التثبيت

### 4.1 Clone and Setup | الاستنساخ والإعداد

```bash
git clone https://github.com/AbuAzad2025/Azad-UAE.git
cd Azad-UAE
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4.2 Database | قاعدة البيانات

```bash
sudo -u postgres createdb azadexa
flask db upgrade
```

### 4.3 Redis | Redis

```bash
sudo systemctl enable redis
sudo systemctl start redis
```

### 4.4 Assets | الأصول

```bash
flask build-assets
```

### 4.5 First Run | التشغيل الأول

```bash
export FLASK_APP=app.py
flask run --host=0.0.0.0 --port=5000
```

## 5. Production Configuration | إعداد الإنتاج

### 5.1 Gunicorn | Gunicorn

```bash
gunicorn -w 4 -b 127.0.0.1:5000 wsgi:app
```

### 5.2 Nginx | Nginx

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

### 5.3 Celery | Celery

```bash
celery -A app.celery worker --loglevel=info --concurrency=4
celery -A app.celery beat --loglevel=info
```

**EN:** Use `systemd` services for auto-start.
**AR:** استخدم خدمات `systemd` للتشغيل التلقائي.

### 5.4 SSL/TLS | SSL/TLS

**EN:** Let's Encrypt for TLS 1.3. Auto-renewal via `certbot renew`. HSTS header enabled.
**AR:** Let's Encrypt لـ TLS 1.3. التجديد التلقائي عبر `certbot renew`. رأس HSTS مُفعّل.

## 6. Docker (Optional) | Docker (اختياري)

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

## 7. Monitoring | المراقبة

| Tool (EN) | الأداة (AR) | Purpose | الغرض | Status | الحالة |
|-----------|-------------|---------|-------|--------|--------|
| `routes/owner/monitoring.py` | `routes/owner/monitoring.py` | Built-in health dashboard | لوحة الصحة المدمجة | Active | نشط |
| Prometheus + Grafana | Prometheus + Grafana | Metrics and dashboards | المقاييس واللوحات | Roadmap Q4 2026 | خارطة الطريق Q4 2026 |
| Sentry | Sentry | Error tracking | تتبع الأخطاء | Roadmap Q4 2026 | خارطة الطريق Q4 2026 |
| UptimeRobot | UptimeRobot | External uptime monitoring | مراقبة التشغيل الخارجية | Recommended | موصى به |

## 8. Scaling | التوسع

| Scale Type (EN) | نوع التوسع | Trigger | المُشغّل | Action | الإجراء |
|-----------------|-----------|---------|---------|--------|---------|
| Vertical | رأسي | CPU > 80% for 5 min | CPU > 80% لـ 5 دقائق | Increase instance size | زيادة حجم المثيل |
| Horizontal | أفقي | Requests > 500/sec | الطلبات > 500/ثانية | Add Gunicorn workers or load balancer | إضافة عمال Gunicorn أو موازن الحمل |
| Database | قاعدة البيانات | Connections > 80% | الاتصالات > 80% | Connection pooling (PgBouncer) | تجميع الاتصالات (PgBouncer) |
| Cache | التخزين المؤقت | Hit rate < 70% | معدل الإصابة < 70% | Increase Redis memory or shard | زيادة ذاكرة Redis أو تقسيمها |

## 9. Backup and Recovery | النسخ الاحتياطي والاستعادة

| Backup (EN) | النسخ (AR) | Frequency | التكرار | Command | الأمر |
|-------------|-----------|-----------|---------|---------|-------|
| Full DB | DB كامل | Daily | يومي | `pg_dump azadexa | gzip > backup.sql.gz` | `pg_dump azadexa | gzip > backup.sql.gz` |
| WAL archive | أرشيف WAL | Continuous | مستمر | PostgreSQL archive_mode | PostgreSQL archive_mode |
| Scoped export | تصدير نطاقي | Weekly | أسبوعي | `flask backup` | `flask backup` |

**EN:** Recovery RPO: 24 hours. RTO: 4 hours.
**AR:** RPO الاستعادة: 24 ساعة. RTO: 4 ساعات.

## 10. Support | الدعم

**EN:** DevOps support: devops@azadsystems.com | Emergency: +972 56 215 0193
**AR:** دعم DevOps: devops@azadsystems.com | طارئ: +972 56 215 0193
