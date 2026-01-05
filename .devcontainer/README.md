# VS Code Dev Container Setup

This folder contains the configuration for running HospitalFlow in a VS Code Dev Container.

## Prerequisites

1. **Docker Desktop** must be installed and running
2. **VS Code** with the **Dev Containers** extension installed

## Getting Started

1. Ensure Docker Desktop is running
2. Open VS Code in this repository
3. Press `F1` or `Cmd+Shift+P` (Mac) / `Ctrl+Shift+P` (Windows/Linux)
4. Select **"Dev Containers: Reopen in Container"**
5. Wait for the container to build and start

## Troubleshooting

If you see the error: `Failed to reopen folder in container Error running 'docker info'`:

1. **Check Docker Desktop is running**: Open Docker Desktop and ensure it's fully started
2. **Verify Docker CLI access**: Run `docker ps` in terminal - it should work without errors
3. **Restart VS Code**: Sometimes VS Code needs a restart to pick up Docker
4. **Check Docker context**: Run `docker context ls` and ensure the correct context is active
5. **Restart Docker Desktop**: Quit and restart Docker Desktop if needed

## Running the Application

Once in the container:

```bash
streamlit run app.py
```

The app will be accessible at `http://localhost:8501` (port forwarding is automatic).

## Container Features

- Python 3.11
- All dependencies from `requirements.txt` installed
- VS Code Python extensions pre-installed
- Port 8501 automatically forwarded
