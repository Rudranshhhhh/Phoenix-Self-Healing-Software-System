"""
Phoenix Agent — Event Type Constants

All internal event type strings used by the EventBus.
Using constants prevents typo-driven bugs in subscriber registrations.
"""

# ------------------------------------------------------------------ #
# Collector Events (published by collector plugins)                  #
# ------------------------------------------------------------------ #
SNAPSHOT_COLLECTED = "SnapshotCollected"

# ------------------------------------------------------------------ #
# Detection Events (published by DetectionEngine)                    #
# ------------------------------------------------------------------ #
INCIDENT_DETECTED = "IncidentDetected"

# ------------------------------------------------------------------ #
# Diagnosis Events (published by DiagnosisEngine)                    #
# ------------------------------------------------------------------ #
INCIDENT_DIAGNOSED = "IncidentDiagnosed"

# ------------------------------------------------------------------ #
# Recovery Events (published by RecoveryEngine)                      #
# ------------------------------------------------------------------ #
RECOVERY_STARTED = "RecoveryStarted"
RECOVERY_FINISHED = "RecoveryFinished"
RECOVERY_FAILED = "RecoveryFailed"

# ------------------------------------------------------------------ #
# Verification Events (published by VerificationEngine)              #
# ------------------------------------------------------------------ #
VERIFICATION_PASSED = "VerificationPassed"
VERIFICATION_FAILED = "VerificationFailed"

# ------------------------------------------------------------------ #
# Escalation Events (published by EscalationEngine)                  #
# ------------------------------------------------------------------ #
ESCALATION_TRIGGERED = "EscalationTriggered"

# ------------------------------------------------------------------ #
# Resolution Events                                                   #
# ------------------------------------------------------------------ #
INCIDENT_RESOLVED = "IncidentResolved"

# ------------------------------------------------------------------ #
# Sandbox / Validation / Git Events (Person 4)                       #
# Published by SandboxPipeline                                        #
# ------------------------------------------------------------------ #

# Pipeline began (sandbox copy being created)
SANDBOX_STARTED = "SandboxStarted"

# Patch was applied to the sandbox copy; validation is running
SANDBOX_PATCH_APPLIED = "SandboxPatchApplied"

# All validation checks passed; Git branch/commit/PR steps are next
SANDBOX_VALIDATED = "SandboxValidated"

# One or more validation checks failed; no branch or PR was created
SANDBOX_REJECTED = "SandboxRejected"

# The fix branch was created and pushed to the remote
SANDBOX_BRANCH_PUSHED = "SandboxBranchPushed"

# A Pull Request was successfully opened on GitHub
SANDBOX_PR_CREATED = "SandboxPRCreated"

# The pipeline itself encountered an unhandled exception
SANDBOX_FAILED = "SandboxFailed"

# ------------------------------------------------------------------ #
# Container State Events                                              #
# ------------------------------------------------------------------ #
CONTAINER_STOPPED = "ContainerStopped"
CONTAINER_RECOVERED = "ContainerRecovered"

# ------------------------------------------------------------------ #
# Service Health Events                                               #
# ------------------------------------------------------------------ #
HEALTH_CHECK_FAILED = "HealthCheckFailed"
HEALTH_CHECK_RESTORED = "HealthCheckRestored"

# ------------------------------------------------------------------ #
# Database Events                                                     #
# ------------------------------------------------------------------ #
DATABASE_DISCONNECTED = "DatabaseDisconnected"
DATABASE_RESTORED = "DatabaseRestored"

# ------------------------------------------------------------------ #
# Redis Events                                                        #
# ------------------------------------------------------------------ #
REDIS_DISCONNECTED = "RedisDisconnected"
REDIS_RESTORED = "RedisRestored"

# ------------------------------------------------------------------ #
# Resource Events                                                     #
# ------------------------------------------------------------------ #
HIGH_CPU_DETECTED = "HighCPUDetected"
HIGH_MEMORY_DETECTED = "HighMemoryDetected"
