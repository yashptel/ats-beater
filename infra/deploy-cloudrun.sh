#!/usr/bin/env bash
set -euo pipefail

# ─── Configuration ──────────────────────────────────────────────────────────
PROJECT_ID="${GCP_PROJECT_ID:?Set GCP_PROJECT_ID}"
REGION="${GCP_REGION:-asia-southeast1}"
SERVICE_NAME="${SERVICE_NAME:-ats-beater}"
REPO_NAME="${REPO_NAME:-ats-beater}"             # Artifact Registry repository
IMAGE_NAME="${IMAGE_NAME:-ats-beater}"
TAG="${1:-latest}"
ENV_FILE="${2:-.env.yaml}"

# ─── Derived ────────────────────────────────────────────────────────────────
AR_HOST="${REGION}-docker.pkg.dev"
FULL_IMAGE="${AR_HOST}/${PROJECT_ID}/${REPO_NAME}/${IMAGE_NAME}:${TAG}"

echo "=== Cloud Run Deployment ==="
echo "Project:  ${PROJECT_ID}"
echo "Region:   ${REGION}"
echo "Service:  ${SERVICE_NAME}"
echo "Image:    ${FULL_IMAGE}"
echo "Env file: ${ENV_FILE}"
echo ""

# ─── 1. Artifact Registry ──────────────────────────────────────────────────
echo "==> Creating Artifact Registry repo (if needed)..."
gcloud artifacts repositories create "${REPO_NAME}" \
    --repository-format=docker \
    --location="${REGION}" \
    --project="${PROJECT_ID}" \
    --quiet 2>/dev/null || true

echo "==> Configuring Docker auth..."
gcloud auth configure-docker "${AR_HOST}" --quiet

# ─── 2. Build & Push ───────────────────────────────────────────────────────
echo "==> Building Docker image (linux/amd64)..."
docker build --platform linux/amd64 -t "${FULL_IMAGE}" -f Dockerfile .

echo "==> Pushing image..."
docker push "${FULL_IMAGE}"

# ─── 3. Deploy ──────────────────────────────────────────────────────────────
echo "==> Deploying to Cloud Run..."
gcloud run deploy "${SERVICE_NAME}" \
    --image="${FULL_IMAGE}" \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --platform=managed \
    --allow-unauthenticated \
    --min-instances=1 \
    --max-instances=5 \
    --memory=2Gi \
    --cpu=2 \
    --timeout=300 \
    --port=8080 \
    --env-vars-file="${ENV_FILE}"

# ─── 4. Print result ───────────────────────────────────────────────────────
echo ""
echo "==> Deployment complete!"
SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --format="value(status.url)")
echo "Service URL: ${SERVICE_URL}"

echo ""
echo "NEXT STEPS:"
echo "  1. Update FRONTEND_URL in .env.yaml to: ${SERVICE_URL}"
echo "  2. Update Google OAuth redirect URI to: ${SERVICE_URL}/auth/google/callback"
echo "  3. Run migrations (one-time):"
echo "     gcloud run services update ${SERVICE_NAME} --region=${REGION} \\"
echo "       --update-env-vars=RUN_MIGRATIONS=true"
echo "     Then hit the service once to trigger migration, then set back to false:"
echo "     gcloud run services update ${SERVICE_NAME} --region=${REGION} \\"
echo "       --update-env-vars=RUN_MIGRATIONS=false"
