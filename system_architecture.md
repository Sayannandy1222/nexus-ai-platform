# NEXUS AI Platform --- System Architecture

> Production-oriented LLM Gateway & LLMOps Platform

NEXUS is a layered, horizontally scalable AI infrastructure platform
providing secure LLM access, provider routing, caching, rate limiting,
reliability controls, and end-to-end observability.

## 1. High-Level Architecture

``` mermaid
flowchart TB
    C[Client / Application] --> N[NGINX<br/>Reverse Proxy + Load Balancer]
    N --> A1[FastAPI API-1]
    N --> A2[FastAPI API-2]

    A1 --> S[Security & Guardrails]
    A2 --> S
    S --> R[Rate Limiting]
    R --> V[Valkey / Redis-Compatible Cache]
    S --> G[LLM Gateway]
    G --> H[Shared Async HTTP Client Pool]
    H --> P1[Mistral]
    H --> P2[Groq]
    H --> P3[Gemini]

    A1 --> M[Prometheus Metrics]
    A2 --> M
    G --> M
    M --> F[Grafana]
    M --> AL[Alertmanager]
    A1 --> T[OpenTelemetry / Tracing]
    A2 --> T
```

## 2. Layered Architecture

### Layer 1 --- Edge

**NGINX + Docker**

NGINX is the single public entry point. It reverse-proxies traffic to
the FastAPI replicas and provides the foundation for horizontal API
scaling.

``` text
Client → NGINX :8080 → API-1 :8000
                    → API-2 :8000
```

### Layer 2 --- API / Application

**Python + FastAPI**

The application exposes:

  Endpoint                     Purpose
  ---------------------------- -----------------------
  `POST /v1/generate`          LLM generation
  `GET /v1/health`             Liveness
  `GET /v1/ready`              Readiness
  `GET /v1/metrics`            Prometheus metrics
  `GET /v1/rate-limit/check`   Rate-limit inspection
  `/docs`                      OpenAPI documentation

The API is designed to be stateless so additional replicas can be added
behind NGINX.

### Layer 3 --- Security & Guardrails

**API-key authentication + request validation**

Requests are authenticated before generation. Missing credentials
produce `401 Unauthorized`. Request-size and input validation controls
protect the gateway from malformed or excessive requests.

### Layer 4 --- Rate Limiting / Control

The rate limiter uses shared Valkey state so API-1 and API-2 do not
maintain isolated counters.

``` text
API-1 ──┐
        ├──→ Shared Valkey → Rate-limit state
API-2 ──┘
```

### Layer 5 --- Cache

**Valkey / Redis-compatible datastore**

Valkey provides shared infrastructure for caching, rate-limit state, and
semantic-cache architecture. This keeps behavior consistent across API
replicas.

### Layer 6 --- LLM Gateway

The LLM gateway separates application logic from individual LLM vendors.

``` text
FastAPI
   ↓
LLM Gateway
   ↓
Provider Router
   ├── Mistral
   ├── Groq
   ├── Gemini
   └── Fake/Test Provider
```

Provider abstraction makes it possible to change or add providers
without coupling the API layer to a vendor-specific implementation.

### Layer 7 --- Reliability & Provider Routing

The gateway tracks provider state and supports the architecture for
retries, fallback, provider health, failure tracking, latency tracking,
and provider selection.

``` mermaid
flowchart LR
    R[Request] --> G[Provider Router]
    G --> P[Selected Provider]
    P --> Q{Success?}
    Q -->|Yes| OK[Return Response]
    Q -->|No| RT[Retry]
    RT --> FB[Fallback / Alternate Provider]
    FB --> OK
```

### Layer 8 --- HTTP Client Infrastructure

A shared asynchronous HTTP client pool is used for provider
communication.

Benefits include:

-   Connection reuse
-   Connection pooling
-   Controlled concurrency
-   Lower connection-establishment overhead
-   Shared lifecycle management

### Layer 9 --- Observability

**Prometheus + Grafana + Alertmanager + OpenTelemetry**

Prometheus exposes and collects metrics such as:

``` text
nexus_llm_requests_total
nexus_llm_errors_total
nexus_llm_retries_total
nexus_llm_fallbacks_total
nexus_llm_provider_requests
nexus_llm_provider_success_rate
nexus_llm_provider_error_rate
nexus_llm_provider_average_latency_seconds
nexus_llm_provider_consecutive_failures
nexus_llm_provider_healthy
nexus_llm_provider_score
nexus_llm_provider_selected_total
```

Grafana provides operational visualization, while Alertmanager provides
alert handling. OpenTelemetry provides tracing foundations.

### Layer 10 --- Infrastructure & CI

**Docker Compose + GitHub Actions**

Current containerized topology:

  Service                Responsibility
  ---------------------- -------------------------------
  `nexus-nginx`          Reverse proxy / load balancer
  `nexus-api-1`          FastAPI replica
  `nexus-api-2`          FastAPI replica
  `nexus-valkey`         Shared cache/state
  `nexus-prometheus`     Metrics collection
  `nexus-grafana`        Dashboards
  `nexus-alertmanager`   Alert management

GitHub Actions validates repository changes automatically.

------------------------------------------------------------------------

## 3. End-to-End Request Flow

``` mermaid
sequenceDiagram
    participant C as Client
    participant N as NGINX
    participant A as FastAPI
    participant S as Security
    participant R as Rate Limiter
    participant V as Valkey
    participant G as LLM Gateway
    participant H as HTTP Pool
    participant P as Provider
    participant M as Metrics

    C->>N: POST /v1/generate
    N->>A: Forward request
    A->>S: Validate API key
    S-->>A: Authorized
    A->>R: Check limit
    R->>V: Shared state
    V-->>R: Allowed
    R-->>A: Continue
    A->>G: Generate
    G->>H: Provider request
    H->>P: HTTPS
    P-->>H: LLM response
    H-->>G: Result
    G-->>A: Generation response
    A->>M: Record metrics
    A-->>N: Response
    N-->>C: Response
```

## 4. Health & Reliability

### Liveness

`GET /v1/health`

Answers: **Is the application process running?**

Validated response:

``` json
{"status":"ok"}
```

### Readiness

`GET /v1/ready`

Answers: **Can this instance safely receive traffic?**

Validated response:

``` json
{"status":"ready","cache":"ok","ping":"True"}
```

Readiness verifies the Valkey dependency.

------------------------------------------------------------------------

## 5. Scalability Architecture

Current:

``` text
              NGINX
             /               API-1   API-2
             \     /
              Valkey
```

Future horizontal scaling:

``` text
                 Load Balancer
                       |
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
      API-1          API-2          API-N
        └──────────────┼──────────────┘
                       |
                    Valkey
```

Because the API tier is stateless, capacity can be increased by adding
replicas rather than redesigning the application.

A future Kubernetes deployment can add Deployments, Services, HPA,
resource limits, pod disruption controls, and automated scheduling.

------------------------------------------------------------------------

## 6. Performance & Cost Optimization

NEXUS applies optimization at multiple layers:

### API

-   Async FastAPI execution
-   Lightweight middleware
-   Stateless replicas
-   Controlled concurrency

### Network / LLM

-   Shared HTTP connection pool
-   Connection reuse
-   Provider routing
-   Retry/fallback controls
-   Provider latency tracking

### Cache

-   Shared Valkey
-   Rate-limit state
-   Semantic-cache architecture
-   Potential reduction of duplicate LLM calls

### Cost model

A major optimization target is reducing unnecessary provider calls:

``` text
Requests
   ↓
Cache Check
 ┌─┴─┐
Hit  Miss
 |     |
Return LLM Call
        ↓
     Cache Result
```

Actual cost savings should be benchmarked against real production
traffic rather than claimed without measurements.

------------------------------------------------------------------------

## 7. Security & Configuration

Secrets are externalized through environment variables rather than
committed to source control.

Examples:

``` text
NEXUS_API_KEY
MISTRAL_API_KEY
GROQ_API_KEY
GEMINI_API_KEY
```

`.env` should remain ignored by Git.

------------------------------------------------------------------------

## 8. Validated Achievements

The development environment has validated:

-   NGINX successfully starts and serves port `8080`.
-   API-1 and API-2 become healthy.
-   Valkey becomes healthy.
-   API-to-Valkey network connectivity works.
-   `/v1/health` returns `200`.
-   `/v1/ready` returns `200` with cache health confirmed.
-   OpenAPI documentation is available.
-   Missing API keys return `401`.
-   Authenticated generation successfully reaches Mistral.
-   LLM metrics increment after generation.
-   Provider health and latency metrics are exposed.
-   Prometheus is running.
-   Grafana is running.
-   Alertmanager is running.
-   Docker Compose can recreate the service topology.
-   API replicas operate behind NGINX.

## 9. Technology Stack

  Area                   Technology
  ---------------------- ------------------------------------
  Language               Python
  API                    FastAPI
  Edge                   NGINX
  Containers             Docker
  Orchestration          Docker Compose
  Cache / Shared State   Valkey
  LLM Gateway            Custom provider abstraction/router
  Providers              Mistral, Groq, Gemini, Fake/Test
  HTTP                   Async shared client pool
  Metrics                Prometheus
  Dashboards             Grafana
  Alerting               Alertmanager
  Tracing                OpenTelemetry
  CI                     GitHub Actions
  API Specification      OpenAPI

## 10. Engineering Principles

NEXUS is built around:

1.  **Separation of concerns** --- each layer has one clear
    responsibility.
2.  **Stateless application replicas** --- horizontal scaling without
    local shared state.
3.  **Provider abstraction** --- avoid vendor lock-in at the application
    layer.
4.  **Shared infrastructure** --- consistent cache and rate-limit
    behavior across replicas.
5.  **Failure-aware design** --- health checks, provider state, retries
    and fallback architecture.
6.  **Observability-first engineering** --- metrics, logs and tracing
    are part of the platform.
7.  **Configuration externalization** --- secrets remain outside source
    code.
8.  **Performance-aware infrastructure** --- connection pooling and
    caching reduce unnecessary overhead.

## 11. Production Evolution Roadmap

### Current

``` text
Docker Compose
+ NGINX
+ FastAPI replicas
+ Valkey
+ Prometheus
+ Grafana
+ Alertmanager
+ GitHub Actions
```

### Next scale

-   Kubernetes
-   Horizontal Pod Autoscaler
-   Resource requests/limits
-   Secrets management
-   Distributed tracing backend
-   Advanced circuit breaking
-   Queue-based asynchronous workloads
-   Multi-region deployment
-   Global traffic management
-   Automated disaster recovery

These are future evolution paths and are not represented as currently
implemented capabilities.

## 12. Architecture Positioning

**NEXUS is not simply an LLM API wrapper.**

It is structured as an **LLM infrastructure and LLMOps platform** with
dedicated layers for:

-   Edge traffic management
-   Secure API access
-   Guardrails
-   Rate limiting
-   Shared caching
-   Provider abstraction
-   Provider routing
-   Reliability
-   Connection pooling
-   Horizontal scaling
-   Metrics
-   Dashboards
-   Alerting
-   Tracing foundations
-   Containerized deployment
-   CI validation

The architecture is designed so individual layers can evolve
independently while preserving a stable external API contract.
