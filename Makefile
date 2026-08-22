.PHONY: up down logs restart-agent restart-backend shell-agent shell-backend demo-crash demo-leak demo-cpu demo-db demo-redis demo-health-break status clean

# =============================================================================
# Phoenix Self-Healing Platform — Developer Makefile
# =============================================================================

up:
	@echo "🔥 Starting Phoenix..."
	docker compose up --build -d
	@echo "✅ Phoenix is running. Dashboard: http://localhost:3000 | API: http://localhost:5000"

down:
	@echo "🛑 Stopping Phoenix..."
	docker compose down

logs:
	docker compose logs -f

logs-agent:
	docker compose logs -f phoenix-agent

logs-backend:
	docker compose logs -f phoenix-backend

status:
	docker compose ps

restart-agent:
	docker compose restart phoenix-agent

restart-backend:
	docker compose restart phoenix-backend

shell-agent:
	docker exec -it phoenix-agent /bin/bash

shell-backend:
	docker exec -it phoenix-backend /bin/bash

# --- Demo failure scenarios (triggers Phoenix self-healing) ---

demo-crash:
	@echo "💥 Triggering backend crash..."
	curl -s http://localhost:8080/crash || true
	@echo "👁 Watch Phoenix detect and recover at http://localhost:3000"

demo-leak:
	@echo "💧 Triggering memory leak..."
	curl -s http://localhost:8080/leak &
	@echo "👁 Watch Phoenix detect HighMemory at http://localhost:3000"

demo-cpu:
	@echo "🔥 Triggering CPU spike..."
	curl -s http://localhost:8080/cpu &
	@echo "👁 Watch Phoenix detect HighCPU at http://localhost:3000"

demo-db:
	@echo "🗄 Stopping postgres to simulate DB failure..."
	docker compose stop postgres
	@echo "👁 Watch Phoenix detect DatabaseUnreachable at http://localhost:3000"

demo-redis:
	@echo "📦 Stopping redis to simulate Redis failure..."
	docker compose stop redis
	@echo "👁 Watch Phoenix detect RedisDown at http://localhost:3000"

demo-health-break:
	@echo "🩺 Breaking health endpoint..."
	curl -s http://localhost:8080/break-health || true
	@echo "👁 Watch Phoenix detect HealthFailure at http://localhost:3000"

demo-restore-db:
	docker compose start postgres

demo-restore-redis:
	docker compose start redis

clean:
	docker compose down -v --remove-orphans
	@echo "🧹 All containers and volumes removed"
