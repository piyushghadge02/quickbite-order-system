# 08 — Submission Checklist

## Code repository
- [ ] Create a GitHub repository, e.g. `quickbite-order-system`.
- [ ] Upload the source code, tests, Dockerfile(s), Docker Compose file, and requirements.
- [ ] Add/update `README.md` with project overview, setup, commands, and API examples.
- [ ] Add this `knowledge-bytes` folder if useful for documentation.
- [ ] Add an architecture diagram.
- [ ] Verify `.env`, secrets, local databases, virtual environments, and caches are excluded as appropriate.
- [ ] Test the README startup instructions on a clean terminal.

## Evidence for evaluation
- [ ] Screenshot of `docker compose ps` with services running.
- [ ] Screenshot of `/health` showing healthy.
- [ ] Screenshot of successful `POST /orders`.
- [ ] Screenshot of `GET /orders/{order_id}` showing later status.
- [ ] RabbitMQ dashboard with queues visible.
- [ ] Worker logs showing event processing.
- [ ] Evidence of at least four failure/scaling scenarios where implemented and safely reproducible.
- [ ] Short demo video or prepared live demonstration.
- [ ] Short report explaining queue rationale, retries, dead-lettering, scaling, and challenges.

## Git safety
Do not commit secrets. Check `git status` and inspect the staged diff before committing. Keep the project repository separate from any unrelated repositories.
