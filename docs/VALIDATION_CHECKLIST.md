╔════════════════════════════════════════════════════════════════════════╗
║           PHOENIX ORCHESTRATOR - IMPLEMENTATION CHECKLIST              ║
║                    (Pre-Docker Validation Complete)                    ║
╚════════════════════════════════════════════════════════════════════════╝

✅ REQUIREMENT 1: INC-001 Counter
   Evidence: phoenix-api/app/incident_store.py (atomic MongoDB $inc)
   Status: DONE - Verified code structure

✅ REQUIREMENT 2: Webhook Authentication  
   Evidence: phoenix-api/app/routers/incidents.py (_verify_webhook_secret)
   Status: DONE - X-Phoenix-Token header validation

✅ REQUIREMENT 3: Loop Guard
   Evidence: phoenix-api/app/routers/incidents.py (_is_loop_guard)
   Status: DONE - Detects phoenix/fix/* branches

✅ REQUIREMENT 4: Deduplication
   Evidence: phoenix-api/app/incident_store.py (check_duplicate)
   Status: DONE - Sparse index on (repo, commit, run_id)

✅ REQUIREMENT 5: Failure Classification
   Evidence: phoenix-api/app/classifier.py (FailureClassifier)
   Status: DONE - Code vs non-code distinction

✅ REQUIREMENT 6: Evidence Extraction
   Evidence: phoenix-api/app/evidence.py (thin adapter)
   Status: DONE - Converts to existing EvidenceInput, no duplication

✅ REQUIREMENT 7: LLM Integration
   Evidence: phoenix-api/app/orchestrator.py (calls LLMEngine.run)
   Status: DONE - Uses existing agent.ai.llm_engine, unmodified

✅ REQUIREMENT 8: Sandbox Integration
   Evidence: phoenix-api/app/orchestrator.py (calls SandboxPipeline.run)
   Status: DONE - Uses existing agent.sandbox, unmodified

✅ REQUIREMENT 9: MongoDB Incident Store
   Evidence: phoenix-api/app/database.py + incident_store.py
   Status: DONE - Collections, indexes, CRUD operations

✅ REQUIREMENT 10: API Endpoints
   Evidence: phoenix-api/app/routers/incidents.py + health.py
   Status: DONE - POST/GET endpoints with authentication

✅ REQUIREMENT 11: Real-Time Status
   Evidence: phoenix-api/app/incident_store.py (timeline tracking)
   Status: DONE - MongoDB updates as pipeline progresses

✅ REQUIREMENT 12: GitHub PR Creation
   Evidence: phoenix-api/app/orchestrator.py (receives from SandboxPipeline)
   Status: DONE - Stores pr_url, pr_number from existing pipeline

✅ REQUIREMENT 13: Git Operations
   Evidence: phoenix-api/app/orchestrator.py (delegates to SandboxPipeline)
   Status: DONE - Branch creation, commit, push handled by existing code

✅ REQUIREMENT 14: Docker Compose Wiring
   Evidence: docker-compose.yml (phoenix-api service on port 8000)
   Status: DONE - All services wired, MongoDB healthcheck added

✅ REQUIREMENT 15: Environment Configuration
   Evidence: phoenix-api/app/config.py + .env.example
   Status: DONE - Fail-fast validation, all vars documented

✅ REQUIREMENT 16: Background Processing
   Evidence: phoenix-api/app/main.py + routers/incidents.py
   Status: DONE - FastAPI BackgroundTasks, 202 Accepted response

✅ REQUIREMENT 17: Non-Code Failure Handling
   Evidence: phoenix-api/app/orchestrator.py (classify + ignore)
   Status: DONE - Marks as "ignored", no branch created

✅ REQUIREMENT 18: Test Scripts
   Evidence: scripts/simulate_ci_failure.sh + simulate_docker_failure.sh
   Status: DONE - Curl-based local tests

⚠️  REQUIREMENT 19: Docker Monitor → Phoenix API Integration
   Status: PARTIAL - http_reporter.py exists but:
   - Targets old Flask backend (port 5000) instead of Phoenix API (port 8000)
   - Missing X-Phoenix-Token header
   - Action: Update BACKEND_URL and add webhook header

❌ REQUIREMENT 20: GitHub Actions report-failure Job
   Status: MISSING - .github/workflows/phoenix-ci.yml exists but:
   - No report-failure job that calls /api/incidents
   - Action: Add report-failure step to workflow

╔════════════════════════════════════════════════════════════════════════╗
║ CRITICAL VERIFICATION: No modifications to existing systems            ║
║                                                                        ║
║ ✓ agent/ai/llm_engine/       — Zero changes                           ║
║ ✓ agent/sandbox/              — Zero changes                           ║
║ ✓ agent/plugins/              — Zero changes (Docker monitor intact)   ║
║ ✓ agent/diagnosis/            — Zero changes                           ║
║ ✓ agent/recovery/             — Zero changes                           ║
║ ✓ agent/detectors/            — Zero changes                           ║
║                                                                        ║
║ Modified (4 files):                                                    ║
║ • .env.example                — Added PHOENIX_* config vars          ║
║ • docker-compose.yml          — Added phoenix-api service             ║
║ • phoenix-api/app/main.py     — Converted stub to real FastAPI app    ║
║ • phoenix-api/requirements.txt — Added pymongo, gitpython, PyGithub   ║
║                                                                        ║
║ New (18 files):                                                        ║
║ • phoenix-api/Dockerfile, config.py, database.py, ...                 ║
║ • scripts/simulate_*.sh, test_phoenix_api_standalone.py               ║
╚════════════════════════════════════════════════════════════════════════╝

SUMMARY: 18/20 requirements fully implemented
         1/20  requirements partial (Docker monitor config)
         1/20  requirements missing (GitHub workflow job)

READY FOR DOCKER TESTING ✅
