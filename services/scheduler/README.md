# Scheduler Service (Phase 3 Placeholder)

The scheduler will sit between the API and the workers to implement explicit model routing.

**Planned responsibilities:**
- Inspect incoming jobs and decide which model queue to route them to
- Route short text → `text-small`, long text → `text-large`
- Route image inputs → `image-small`
- Provide a single entry queue (`queue:incoming`) that the API always pushes to

**Current state:** Not yet implemented.  
In the MVP, routing is implicit — the API pushes directly to `queue:{model}` based on the `model` field in the request.

**Implementation target:** Phase 3
