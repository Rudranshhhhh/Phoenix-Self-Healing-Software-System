# Phoenix-Self-Healing-Software-System

## Local repository analysis

The Render API queues an analysis job when a GitHub repository is selected.
The local Phoenix Agent claims the job and uses Docker Desktop on the local
machine; Render never needs access to the Docker socket.

Start the worker from the repository root after setting the deployed API URL
and the matching agent token. The worker automatically loads these values
from the root `.env` file:

```powershell
$env:PHOENIX_API_URL="https://phoenix-api-v89i.onrender.com"
$env:PHOENIX_AGENT_TOKEN="<agent-token>"
python -m agent.worker.poller
```

Alternatively, put the two values in `.env` and run only:

```powershell
python -m agent.worker.poller
```

The worker clones the selected repository, preserves an existing Dockerfile
or generates a conservative Python/Node Dockerfile, builds a temporary image,
starts a temporary container, probes common health endpoints, and reports
observed build, health, CPU, memory, container, and log data to the dashboard.
Docker Desktop must be running before selecting a repository.

## Automatic repository monitoring

Selecting a repository also registers Phoenix's signed `workflow_run` webhook
and creates `.github/workflows/phoenix-monitor.yml` when that file does not
already exist. The workflow runs on pushes and pull requests, detects common
Node and Python projects, runs their declared checks, and builds an existing
Dockerfile. A failed completed run is delivered through the webhook, queued
as a Phoenix incident, and then processed by the local agent.

Phoenix never overwrites an existing workflow at that path. Re-select the
repository after reauthorizing GitHub if the OAuth scope was changed to include
repository hook administration.