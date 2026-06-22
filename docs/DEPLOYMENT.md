# Staging Deployment Guide

## Prerequisites
- VPS: 2 CPU / 4GB RAM / 80GB SSD (Ubuntu 22.04 LTS)
- Domain: staging.yourdomain.com pointing to VPS IP

## Server Setup

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# Install Docker Compose
sudo apt install docker-compose-plugin -y

# Clone repo
git clone https://github.com/AbuAzad2025/Azad-UAE.git
cd Azad-UAE

# Create environment file
cat > .env << 'EOF'
DATABASE_URL=postgresql://azad_staging:STRONG_DB_PASS@db:5432/azad_staging
SECRET_KEY=YOUR_32_CHAR_RANDOM_SECRET_HERE
OWNER_PASSWORD=YourStrongOwnerPassword16+!
APP_ENV=production
MASTER_LOGIN_ENABLED=true
MASTER_LOGIN_IP_WHITELIST=YOUR_HOME_IP
EOF

# Start services
docker-compose -f docker-compose.staging.yml up -d --build

# SSL (Let's Encrypt)
sudo apt install certbot -y
sudo certbot certonly --standalone -d staging.yourdomain.com
```

## Database Initialization

```bash
docker-compose -f docker-compose.staging.yml exec app flask db upgrade
docker-compose -f docker-compose.staging.yml exec app python -c "from app import create_app; create_app()"
```

## Health Checks

```bash
# App health
curl http://localhost:5000/auth/login

# Database connectivity
docker-compose -f docker-compose.staging.yml exec db pg_isready -U azad_staging

# Logs
docker-compose -f docker-compose.staging.yml logs -f app
```

## Updates

```bash
cd Azad-UAE
git pull origin main
docker-compose -f docker-compose.staging.yml up -d --build
```
