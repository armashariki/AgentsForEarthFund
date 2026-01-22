# Grant Proposal Analyzer - Enterprise Deployment Guide

This guide covers deploying the Grant Proposal Analyzer to an internal enterprise web server with support for 5-10 concurrent users.

## Quick Start

### Prerequisites
- Docker Engine 20.10+ and Docker Compose v2+
- At least one LLM API key (Anthropic recommended)
- 4GB RAM minimum (8GB recommended for concurrent users)
- 2 CPU cores minimum

### Development Deployment (Single User)

```bash
# 1. Copy environment template and add your API keys
cp .env.example .env
# Edit .env with your API keys

# 2. Build and run
docker compose up --build

# 3. Access at http://localhost:8501
```

### Production Deployment (5-10 Concurrent Users)

```bash
# 1. Configure environment
cp .env.example .env
# Edit .env with your API keys and generate a secure COOKIE_SECRET:
# openssl rand -hex 32

# 2. Set up SSL certificates (see SSL section below)

# 3. Deploy with production configuration
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# 4. Scale if needed (3 replicas recommended for 5-10 users)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --scale app=3
```

---

## Architecture Overview

```
                    ┌─────────────────┐
                    │   Load Balancer │
                    │     (Nginx)     │
                    │   Port 80/443   │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
        ┌─────▼─────┐  ┌─────▼─────┐  ┌─────▼─────┐
        │  App #1   │  │  App #2   │  │  App #3   │
        │ Streamlit │  │ Streamlit │  │ Streamlit │
        │  :8501    │  │  :8501    │  │  :8501    │
        └───────────┘  └───────────┘  └───────────┘
              │              │              │
              └──────────────┼──────────────┘
                             │
                    ┌────────▼────────┐
                    │  Shared Volume  │
                    │    /output      │
                    └─────────────────┘
```

---

## Configuration Files

| File | Purpose |
|------|---------|
| `Dockerfile` | Multi-stage build for production image |
| `docker-compose.yml` | Base configuration |
| `docker-compose.prod.yml` | Production overrides (nginx, scaling) |
| `.env` | Environment variables (API keys) |
| `nginx/nginx.conf` | Reverse proxy configuration |

---

## SSL Certificate Setup

### Option 1: Self-Signed (Development/Internal)

```bash
mkdir -p nginx/ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/ssl/key.pem \
  -out nginx/ssl/cert.pem \
  -subj "/CN=grant-analyzer.internal"
```

### Option 2: Corporate CA Certificate

Place your corporate certificates in `nginx/ssl/`:
- `cert.pem` - Certificate file
- `key.pem` - Private key file

### Option 3: Let's Encrypt (Public-Facing)

For public deployments, use certbot with DNS validation or modify nginx config for HTTP-01 challenge.

---

## Resource Sizing

### Recommended for 5-10 Concurrent Users

| Component | CPU | Memory | Replicas |
|-----------|-----|--------|----------|
| App (Streamlit) | 2 cores | 4GB | 3 |
| Nginx | 0.5 cores | 512MB | 1 |
| **Total** | 6.5 cores | 12.5GB | - |

### Why These Numbers?

- Each analysis takes 5-15 minutes with significant LLM API calls
- Memory is needed for document processing and AI model responses
- 3 replicas ensure availability if one container restarts
- Nginx handles WebSocket connections for real-time updates

---

## Deployment Commands

### Build & Start

```bash
# Development
docker compose up --build

# Production (detached)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# View logs
docker compose logs -f app

# View specific replica logs
docker compose logs -f app_1
```

### Scaling

```bash
# Scale to 3 instances
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --scale app=3

# Scale down
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --scale app=1
```

### Updates & Maintenance

```bash
# Pull latest code and rebuild
git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# Rolling restart (zero downtime)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-deps app

# Complete restart
docker compose -f docker-compose.yml -f docker-compose.prod.yml down
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### Cleanup

```bash
# Stop containers
docker compose down

# Stop and remove volumes
docker compose down -v

# Remove images
docker compose down --rmi all
```

---

## Health Monitoring

### Health Check Endpoints

- **Nginx**: `http://your-server/health`
- **Streamlit**: `http://your-server/_stcore/health`

### Monitoring Commands

```bash
# Check container status
docker compose ps

# Check health status
docker inspect --format='{{json .State.Health}}' grant-analyzer

# View resource usage
docker stats

# Check logs for errors
docker compose logs --tail=100 app | grep -i error
```

---

## Security Considerations

### API Key Management

- **Never** commit `.env` files to version control
- Use Docker secrets for Swarm deployments
- Consider HashiCorp Vault for enterprise key management

### Network Security

- The nginx config includes:
  - HTTPS enforcement
  - Security headers (XSS, CSRF protection)
  - Rate limiting (10 req/s per IP)
  - Connection limits (10 concurrent per IP)

### Container Security

- Non-root user inside container
- Read-only .env mount
- Resource limits prevent runaway processes

---

## Troubleshooting

### Container Won't Start

```bash
# Check logs
docker compose logs app

# Verify .env file exists
ls -la .env

# Test API key
curl -H "x-api-key: $ANTHROPIC_API_KEY" \
  https://api.anthropic.com/v1/messages
```

### WebSocket Connection Issues

Streamlit requires WebSocket support. Ensure:
1. Nginx proxy headers are configured (included in nginx.conf)
2. No corporate proxy blocking WebSocket upgrades
3. Check browser console for connection errors

### Performance Issues

```bash
# Check resource usage
docker stats

# Increase memory limits in docker-compose.yml
# Under deploy > resources > limits > memory

# Scale up replicas
docker compose up -d --scale app=5
```

### SSL Certificate Issues

```bash
# Verify certificates
openssl x509 -in nginx/ssl/cert.pem -text -noout

# Check nginx can read certs
docker compose exec nginx nginx -t
```

---

## Enterprise Integration

### Behind Corporate Proxy

Add to Dockerfile or docker-compose.yml environment:

```yaml
environment:
  - HTTP_PROXY=http://proxy.corp.com:8080
  - HTTPS_PROXY=http://proxy.corp.com:8080
  - NO_PROXY=localhost,127.0.0.1
```

### Active Directory / SSO

Streamlit doesn't natively support enterprise SSO. Options:
1. Use nginx auth_request module with your identity provider
2. Deploy behind an enterprise API gateway (Kong, Apigee)
3. Use a sidecar authentication proxy

### Logging to Enterprise Systems

Modify docker-compose logging driver:

```yaml
logging:
  driver: syslog
  options:
    syslog-address: "tcp://your-siem.corp.com:514"
    tag: "grant-analyzer"
```

---

## Backup & Recovery

### Backup Output Files

```bash
# Backup output directory
tar -czvf backup-$(date +%Y%m%d).tar.gz output/

# Or use volume backup
docker run --rm -v grant-analyzer_output:/data -v $(pwd):/backup \
  alpine tar cvf /backup/output-backup.tar /data
```

### Disaster Recovery

1. Keep `.env.example` updated with required variables
2. Document any custom nginx configurations
3. Store SSL certificates in secure backup
4. Tag Docker images for rollback capability

---

## Support

For issues specific to this deployment:
1. Check container logs: `docker compose logs`
2. Verify API keys are valid
3. Ensure sufficient resources are allocated
4. Review nginx access/error logs

For application bugs, submit issues to the project repository.
