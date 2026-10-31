# Phoenix-Self-Healing-Software-System

## Local repository analysis

The Render API queues an analysis job when a GitHub repository is selected.
The local Phoenix Agent claims the job and uses Docker Desktop on the local
machine; Render never needs access to the Docker socket.

Start the worker from the repository root after setting the deployed API URL
and the matching agent token:

```powershell
$env:PHOENIX_API_URL="https://phoenix-api-v89i.onrender.com"
$env:PHOENIX_AGENT_TOKEN="<agent-token>"
python -m agent.worker.poller
```

The worker clones the selected repository, preserves an existing Dockerfile
or generates a conservative Python/Node Dockerfile, builds a temporary image,
starts a temporary container, probes common health endpoints, and reports
observed build, health, CPU, memory, container, and log data to the dashboard.
Docker Desktop must be running before selecting a repository.