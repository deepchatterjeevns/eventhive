#!/usr/bin/env bash
set -e

eval $(minikube docker-env)

docker build -t eventhive-auth:latest ./auth_service
docker build -t eventhive-booking:latest ./booking_service

kubectl apply -f k8s/mysql-statefulset.yaml
kubectl apply -f k8s/auth-deployment.yaml
kubectl apply -f k8s/booking-deployment.yaml
kubectl apply -f k8s/ingress.yaml

kubectl rollout status deployment/auth-service --timeout=90s
kubectl rollout status deployment/booking-service --timeout=90s