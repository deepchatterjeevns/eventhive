#!/usr/bin/env bash
# Build images into the Minikube Docker daemon and apply the Kubernetes manifests.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! kubectl cluster-info >/dev/null 2>&1; then
  echo "No reachable Kubernetes cluster. Start one with: minikube start --driver=docker" >&2
  exit 1
fi

# Build inside Minikube's Docker daemon so imagePullPolicy: Never can find them.
if command -v minikube >/dev/null 2>&1; then
  eval "$(minikube docker-env)"
fi

echo "==> Building images"
docker build -t eventhive-auth:latest ./auth_service
docker build -t eventhive-booking:latest ./booking_service

echo "==> Applying config (ConfigMap + Secret must exist before workloads)"
kubectl apply -f k8s/config.yaml

echo "==> Applying MySQL StatefulSet and waiting for readiness"
kubectl apply -f k8s/mysql-statefulset.yaml
kubectl wait --for=condition=ready pod/mysql-0 --timeout=300s

echo "==> Running one-shot migrate + seed job"
kubectl delete job eventhive-migrate --ignore-not-found
kubectl apply -f k8s/migrate-job.yaml
kubectl wait --for=condition=complete job/eventhive-migrate --timeout=300s

echo "==> Applying services"
kubectl apply -f k8s/auth-deployment.yaml
kubectl apply -f k8s/booking-deployment.yaml
kubectl apply -f k8s/ingress.yaml

kubectl rollout status deployment/auth-service --timeout=180s
kubectl rollout status deployment/booking-service --timeout=180s

echo
echo "Done. Run 'minikube ip' and map eventhive.local to that address in /etc/hosts:"
echo "  curl http://eventhive.local/auth/api/health/"
echo "  curl http://eventhive.local/booking/api/events/"
