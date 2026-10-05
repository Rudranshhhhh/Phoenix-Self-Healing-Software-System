"""
Phoenix Agent — Main Entry Point

This file is an orchestrator ONLY.
It wires all modules together and starts the scheduler.
It contains ZERO business logic.

Startup sequence:
  1. Load settings
  2. Initialise EventBus
  3. Register collector plugins
  4. Build all engines (detection, diagnosis, recovery, verification, escalation)
  5. Build Code Patch Engine (LLM → Sandbox → Git → PR) [Person 4]
  6. Build reporters and connect WebSocket
  7. Start CollectorScheduler (spawns daemon threads)
  8. Block main thread forever (all work is in daemon threads)
"""
from __future__ import annotations

import logging
import signal
import sys
import time

from agent.ai.advisor import AIAdvisor
from agent.ai.grok_client import GrokClient
from agent.config.settings import settings
from agent.detectors.detection_engine import DetectionEngine
from agent.detectors.rules.container_rules import ContainerDownRule, RepeatedRestartRule
from agent.detectors.rules.resource_rules import HighCPURule, HighMemoryRule
from agent.detectors.rules.service_rules import (
    DatabaseUnreachableRule,
    HealthEndpointFailureRule,
    RedisDownRule,
)
from agent.diagnosis.diagnosis_engine import DiagnosisEngine
from agent.escalation.escalation_engine import EscalationEngine
from agent.events.bus import EventBus
from agent.plugins.docker.collector import DockerCollector
from agent.plugins.health.collector import HealthCollector
from agent.plugins.logs.collector import LogsCollector
from agent.plugins.postgres.collector import PostgresCollector
from agent.plugins.redis.collector import RedisCollector
from agent.plugins.system.collector import SystemCollector
from agent.plugins.registry import PluginRegistry
from agent.recovery.recovery_engine import RecoveryEngine
from agent.recovery.strategies.restart_container import RestartContainerStrategy
from agent.recovery.strategies.restart_database import RestartDatabaseStrategy
from agent.recovery.strategies.restart_redis import RestartRedisStrategy
from agent.recovery.strategies.retry_health import RetryHealthStrategy
from agent.recovery.strategies.wait_and_retry import WaitAndRetryStrategy
from agent.reporters.http_reporter import HTTPReporter
from agent.reporters.reporter_service import ReporterService
from agent.reporters.websocket_reporter import WebSocketReporter
from agent.sandbox.code_patch_engine import CodePatchEngine
from agent.scheduler.collector_scheduler import CollectorScheduler
from agent.verification.verification_engine import VerificationEngine

# ============================================================================ #
# Logging Configuration                                                          #
# ============================================================================ #

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("phoenix.agent")


# ============================================================================ #
# Bootstrap                                                                      #
# ============================================================================ #

def bootstrap() -> CollectorScheduler:
    """
    Wire all Phoenix components.
    Returns a started CollectorScheduler; main thread blocks until shutdown.
    """
    logger.info("=" * 60)
    logger.info("🔥 Phoenix Agent starting up")
    logger.info("=" * 60)
    logger.info("Backend: %s", settings.backend_url)
    logger.info("Grok AI: %s", "enabled" if settings.grok_enabled else "disabled")
    logger.info("Escalation threshold: %d retries", settings.escalation_threshold)
    logger.info(
        "Code Patch Engine: %s",
        "enabled" if settings.github_token else "disabled (set GROQ_API_KEY + GITHUB_TOKEN)",
    )

    # ------------------------------------------------------------------ #
    # 1. Event Bus                                                         #
    # ------------------------------------------------------------------ #
    bus = EventBus()

    # ------------------------------------------------------------------ #
    # 2. Plugin Registry + Collectors                                      #
    # ------------------------------------------------------------------ #
    registry = PluginRegistry()

    # Docker collector — monitors container status, CPU, memory
    docker_col = DockerCollector(
        service="sample-backend",
        container_name=settings.sample_backend_container,
        docker_socket=settings.docker_socket,
    )
    registry.register(docker_col)

    # Health endpoint collector
    health_col = HealthCollector(
        service="sample-backend",
        health_url=f"{settings.sample_backend_url}/health",
        container_name=settings.sample_backend_container,
    )
    registry.register(health_col)

    # PostgreSQL connectivity collector
    pg_col = PostgresCollector(
        service="postgres",
        container_name="phoenix-postgres",
        host=settings.postgres_host,
        port=settings.postgres_port,
        user=settings.postgres_user,
        password=settings.postgres_password,
        database=settings.postgres_db,
    )
    registry.register(pg_col)

    # Redis connectivity collector
    redis_col = RedisCollector(
        service="redis",
        container_name="phoenix-redis",
        host=settings.redis_host,
        port=settings.redis_port,
    )
    registry.register(redis_col)

    # Docker logs collector
    logs_col = LogsCollector(
        service="sample-backend",
        container_name=settings.sample_backend_container,
        docker_socket=settings.docker_socket,
        tail_lines=settings.log_tail_lines,
    )
    registry.register(logs_col)

    # Host system metrics collector
    system_col = SystemCollector()
    registry.register(system_col)

    logger.info("PluginRegistry: %d collectors registered", len(registry))

    # ------------------------------------------------------------------ #
    # 3. Detection Engine                                                  #
    # ------------------------------------------------------------------ #
    detection_rules = [
        ContainerDownRule(),
        RepeatedRestartRule(restart_threshold=settings.restart_count_delta_threshold),
        HighCPURule(threshold_percent=settings.cpu_threshold_percent),
        HighMemoryRule(threshold_percent=settings.memory_threshold_percent),
        DatabaseUnreachableRule(),
        RedisDownRule(),
        HealthEndpointFailureRule(
            latency_threshold_ms=settings.health_latency_threshold_ms
        ),
    ]
    DetectionEngine(bus=bus, rules=detection_rules)

    # ------------------------------------------------------------------ #
    # 4. AI Advisor (Grok)                                                 #
    # ------------------------------------------------------------------ #
    ai_advisor = None
    if settings.grok_enabled and settings.grok_api_key:
        grok_client = GrokClient(
            api_key=settings.grok_api_key,
            model=settings.grok_model,
            timeout_seconds=settings.grok_timeout_seconds,
        )
        ai_advisor = AIAdvisor(grok_client=grok_client)
        logger.info("AI Advisor: Grok client initialised (model=%s)", settings.grok_model)
    else:
        logger.warning("AI Advisor: Grok disabled or API key not set — skipping AI enrichment")

    # ------------------------------------------------------------------ #
    # 5. Diagnosis Engine                                                  #
    # ------------------------------------------------------------------ #
    DiagnosisEngine(bus=bus, ai_advisor=ai_advisor)

    # ------------------------------------------------------------------ #
    # 6. Recovery Engine                                                   #
    # ------------------------------------------------------------------ #
    postgres_dsn = (
        f"host={settings.postgres_host} port={settings.postgres_port} "
        f"user={settings.postgres_user} password={settings.postgres_password} "
        f"dbname={settings.postgres_db}"
    )

    recovery_strategies = [
        RetryHealthStrategy(
            health_url=f"{settings.sample_backend_url}/health",
            max_attempts=settings.health_retry_attempts,
            delay_seconds=settings.health_retry_delay_seconds,
        ),
        WaitAndRetryStrategy(wait_seconds=30),
        RestartContainerStrategy(
            docker_socket=settings.docker_socket,
            wait_timeout_seconds=settings.recovery_timeout_seconds,
        ),
        RestartDatabaseStrategy(
            docker_socket=settings.docker_socket,
            postgres_container_name="phoenix-postgres",
            postgres_dsn=postgres_dsn,
            wait_timeout_seconds=settings.recovery_timeout_seconds,
        ),
        RestartRedisStrategy(
            docker_socket=settings.docker_socket,
            redis_container_name="phoenix-redis",
            redis_host=settings.redis_host,
            redis_port=settings.redis_port,
        ),
    ]
    RecoveryEngine(bus=bus, strategies=recovery_strategies)

    # ------------------------------------------------------------------ #
    # 7. Verification Engine                                               #
    # ------------------------------------------------------------------ #
    VerificationEngine(
        bus=bus,
        registry=registry,
        escalation_threshold=settings.escalation_threshold,
        verify_wait_seconds=5.0,
    )

    # ------------------------------------------------------------------ #
    # 8. Escalation Engine                                                 #
    # ------------------------------------------------------------------ #
    EscalationEngine(bus=bus)

    # ------------------------------------------------------------------ #
    # 9. Code Patch Engine — LLM diagnosis → Sandbox → Git → PR           #
    # (Person 4 module)                                                    #
    # Subscribes to INCIDENT_DIAGNOSED. Runs in background daemon threads.#
    # Disabled automatically when GROQ_API_KEY is not set.                #
    # ------------------------------------------------------------------ #
    CodePatchEngine(bus=bus)

    # ------------------------------------------------------------------ #
    # 10. Reporters                                                        #
    # ------------------------------------------------------------------ #
    http_reporter = HTTPReporter(backend_url=settings.backend_url)
    ws_reporter = WebSocketReporter(backend_url=settings.backend_url)
    ws_reporter.connect()
    ReporterService(bus=bus, http_reporter=http_reporter, ws_reporter=ws_reporter)

    # ------------------------------------------------------------------ #
    # 11. Scheduler — starts all collector threads                        #
    # ------------------------------------------------------------------ #
    intervals = {
        "docker": settings.poll_docker_seconds,
        "health": settings.poll_health_seconds,
        "postgres": settings.poll_db_seconds,
        "redis": settings.poll_redis_seconds,
        "logs": settings.poll_logs_seconds,
        "system": 10,
    }
    scheduler = CollectorScheduler(registry=registry, bus=bus, intervals=intervals)
    scheduler.start()

    logger.info("🔥 Phoenix Agent is running — %d collector threads active", scheduler.thread_count)
    return scheduler


# ============================================================================ #
# Entry Point                                                                    #
# ============================================================================ #

def main() -> None:
    scheduler = bootstrap()

    def _shutdown(signum, frame):
        logger.info("Phoenix Agent: received signal %d — shutting down", signum)
        scheduler.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    # Block main thread — all real work is in daemon threads
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        scheduler.stop()
        logger.info("Phoenix Agent: stopped")


if __name__ == "__main__":
    main()
