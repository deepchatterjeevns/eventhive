# EventHive – Distributed Event Booking System (Backend)

## 1. Project Overview

**EventHive** is a distributed backend system developed using **Django and Python**, designed to handle **high-concurrency event ticket booking** scenarios reliably.

The project follows a **microservices architecture** with two independent services:
- **Authentication Service** – Handles user management and JWT authentication
- **Booking Service** – Manages events, tickets, and concurrency-safe bookings

The system demonstrates real-world backend engineering concepts such as:
- Microservices design
- JWT-based authentication
- Database transactions and row-level locking
- Dockerized development
- Kubernetes deployment

---

## 2. Problem Statement

In real-world booking platforms (concerts, events, movie tickets), multiple users may attempt to book the **same seat at the same time**.

Without proper concurrency handling, this can result in:
- Double booking of tickets
- Inconsistent database state
- Poor user experience and loss of trust

**EventHive** solves this problem by implementing **database-level concurrency control** using transactions and row-level locking.

---

## 3. Objectives

- Build a scalable backend using Django and REST APIs
- Design services following microservice principles
- Implement secure JWT-based authentication
- Prevent race conditions in ticket booking
- Ensure ACID-compliant database operations
- Containerize services using Docker
- Deploy services on Kubernetes (Minikube)
- Provide reproducible setup and documentation

---

## 4. Technology Stack

| Layer | Technology |
|-----|-----------|
| Programming Language | Python 3.11 |
| Backend Framework | Django, Django REST Framework |
| Database | MySQL 8 |
| Authentication | JWT (SimpleJWT) |
| Containerization | Docker |
| Orchestration | Kubernetes (Minikube) |
| Web Server | Gunicorn |
| API Testing | Postman / curl |

---