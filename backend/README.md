# TigonD Intelligent Data Platform — Phase 3.1

This service is the on-premises core for TigonD. It supports PostgreSQL connection testing, durable metadata, Vault-backed credentials, Keycloak roles, schema discovery, sampled EDA, quality metrics, versioned NiFi execution, and an audited read-only AI copilot.

The copilot is CPU-first. It always has a deterministic grounded reasoning fallback and can optionally use a local Ollama model. It receives platform metadata only—source passwords remain in Vault—and all assistant reads are written to the audit trail.

Phase 3.2 adds the AI Pipeline Designer. `POST /api/v1/pipeline-proposals` converts a natural-language requirement into a versioned draft containing runtime selection, schedule, source-to-target mappings, transformations, quality gates, assumptions and risks. Proposals are deliberately non-executable; later approval is required before they can enter the existing NiFi compilation path.

Phase 3.2 is now complete: visual edits create immutable child versions, validation checks mappings and runtime constraints, version comparison explains every change, and an explicit administrator/developer decision can compile a validated NiFi proposal. Compilation creates a generated flow only; deployment and start remain separate privileged actions.

## Run locally

```bash
cd backend
docker compose up --build
```

- TigonD: `http://localhost:3000`
- API documentation: `http://localhost:8000/docs`
- Keycloak: `http://localhost:8080` (`admin` / `admin` for local administration)
- Vault: `http://localhost:8200`
- NiFi: `http://localhost:18080`
- Ollama: `http://localhost:11434` (optional; disabled by default)

To enable the local model, pull `qwen2.5:3b` into Ollama and set `TIGOND_OLLAMA_ENABLED=true`. The rules engine remains available when Ollama is offline.

The imported TigonD user is `admin` with temporary password `ChangeMe123!`.

## Test

```bash
cd backend
PYTHONPATH=. pytest -q
```

Passwords are never stored in metadata or returned by the API. The development stack uses Vault dev mode and temporary demonstration passwords; production must use initialized Vault storage, TLS, rotated secrets, and non-default Keycloak credentials.
