# Docker images

Images are split to match the **three FastAPI ports** locally: Phase 1, Phase 2, and Phase 3 are separate containers. Frontends each have an optional image (Vercel usually builds Next/Vite **without** Docker).

## Build (repository root)

```bash
docker build -f docker/Dockerfile.phase1 -t capstone-phase1 .
docker build -f docker/Dockerfile.phase2 -t capstone-phase2 .
docker build -f docker/Dockerfile.phase3 -t capstone-phase3 .

docker build -f docker/Dockerfile.user_portal -t capstone-user-portal \
  --build-arg VITE_API_URL=https://YOUR-PHASE3-HOST .

docker build -f docker/Dockerfile.internal_dashboard -t capstone-internal-dashboard \
  --build-arg NEXT_PUBLIC_PHASE1_API_URL=https://YOUR-PHASE1-HOST \
  --build-arg NEXT_PUBLIC_PHASE2_API_URL=https://YOUR-PHASE2-HOST \
  --build-arg NEXT_PUBLIC_PHASE3_API_URL=https://YOUR-PHASE3-HOST .
```

## Render notes

- Create **three Web Services** from the same GitHub repo; set **Dockerfile path** per service to the matching file under `docker/`.
- Set **environment variables** on each service to match `.env.sample` (secrets in the Render dashboard, not in the image).
- **Phase 3** must receive `FAQ_AGENT_URL` pointing at Phase 2’s public URL, for example `https://your-phase2.onrender.com/api/chat`.
- **Phase 2** Chroma data lives under `backend/phase2_factsheet_rag/chroma_db`. Attach a **persistent disk** at that path if indexes should survive redeploys.
- Each service listens on Render’s `PORT`; the Dockerfiles already use `${PORT:-…}`.

## Vercel notes

- Typical setup: **two projects** (user portal + internal dashboard), root directories `frontend/user_portal` and `frontend/internal_dashboard`, framework presets **Vite** and **Next.js**.
- **User portal:** set `VITE_API_URL` to the public Phase 3 origin (no path).
- **Internal dashboard:** set `NEXT_PUBLIC_PHASE1_API_URL`, `NEXT_PUBLIC_PHASE2_API_URL`, and `NEXT_PUBLIC_PHASE3_API_URL` to the three backend origins (no trailing slash).

## GitHub Actions scheduler

After deploy, set repository secrets `SCHEDULER_PHASE1_URL` and `SCHEDULER_PHASE2_URL` to the Phase 1 and Phase 2 **base URLs** (see `docs/Implementation.md` §9).
