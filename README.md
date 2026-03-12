# AtomicSeats (EventHive) – Distributed Event Booking System

## 1. Project Overview

**AtomicSeats** is a distributed backend system developed using **Django and Python**, designed to handle **high-concurrency event ticket booking** scenarios reliably.

The project follows a **microservices architecture** with two independent services:
- **Authentication Service** – Handles user management and JWT authentication.
- **Booking Service** – Manages events, tickets, and concurrency-safe bookings.

The system demonstrates real-world backend engineering concepts such as:
- Microservices design
- JWT-based authentication
- Database transactions and pessimistic row-level locking
- Dockerized development
- Kubernetes deployment on AWS EKS

---

## 2. Problem Statement

In real-world booking platforms (concerts, events, movie tickets), multiple users may attempt to book the **same seat at the same time**.

Without proper concurrency handling, this can result in:
- Double booking of tickets
- Inconsistent database state
- Poor user experience and loss of trust

**AtomicSeats** solves this problem by implementing **database-level concurrency control** using atomic transactions and strict row-level locking (`select_for_update`).

---

## 3. Objectives

- Build a scalable backend using Django and REST APIs.
- Design services following microservice principles.
- Implement secure JWT-based authentication (stateless validation).
- Prevent race conditions in ticket booking.
- Ensure ACID-compliant database operations.
- Containerize services using Docker.
- Deploy services on AWS Elastic Kubernetes Service (EKS) using an Application Load Balancer (ALB).

---

## 4. Technology Stack

| Layer | Technology |
|-----|-----------|
| **Programming Language** | Python 3.11 |
| **Backend Framework** | Django, Django REST Framework |
| **Database** | MySQL 8.0 (AWS RDS) |
| **Authentication** | JWT (SimpleJWT) |
| **Containerization** | Docker, AWS ECR |
| **Orchestration** | Kubernetes (AWS EKS, Minikube for local testing) |
| **Web Server** | Gunicorn |
| **API Testing** | Postman / cURL |

---

## 5. System Architecture

*(Insert your Architecture Diagram image here from the `docs/` folder)*
![System Architecture](docs/architecture.png)

The system routes traffic through an AWS ALB Ingress Controller. The `Auth Service` handles identity and issues a JWT. The `Booking Service` intercepts requests, validates the JWT statelessly using a shared secret, and interacts with the MySQL database using Pessimistic Write Locks to secure ticket inventory.

---

## 6. API Endpoints

| Method | Endpoint | Description | Service |
| :--- | :--- | :--- | :--- |
| **POST** | `/auth/api/token/` | Login and receive JWT access token | Auth Service |
| **POST** | `/booking/api/events/` | Admin creates a new event | Booking Service |
| **GET** | `/booking/api/events/` | User lists available events and seats | Booking Service |
| **POST** | `/booking/api/book/` | User books a ticket (Requires JWT) | Booking Service |

---

## 7. Setup & Deployment Instructions

### Local Testing (Minikube)
1. Clone the repository: `git clone <your-repo-url>`
2. Start Minikube: `minikube start --driver=docker`
3. Enable Ingress: `minikube addons enable ingress`
4. Run the deployment script: `./scripts/build_and_deploy_local.sh`
5. Map `eventhive.local` to your Minikube IP in your `/etc/hosts` file.

### Production Deployment (AWS EKS)
1. Ensure your AWS CLI is configured and `kubectl` is mapped to your EKS cluster.
2. Update the AWS Account ID and Region in `./scripts/build_and_push_aws.sh`.
3. Run the script to build, tag, and push Docker images to AWS ECR and apply the K8s manifests:
   ```bash
   chmod +x ./scripts/build_and_push_aws.sh
   ./scripts/build_and_push_aws.sh