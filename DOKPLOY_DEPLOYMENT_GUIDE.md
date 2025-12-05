# Dokploy Deployment Guide (Final)

This guide details how to deploy the Fidden Backend using **separate Application services** and your **External Redis Cloud**.

## Prerequisites

1.  **Dokploy Server**: Installed and accessible.
2.  **GitHub Repository**: `fidden-backend` connected.
3.  **Domain**: Pointed to your server IP.
4.  **Redis URL**: `redis://default:rZZSZXlgx2hNPDi7iNTayckrDj9uAGNg@redis-13197.c114.us-east-1-4.ec2.cloud.redislabs.com:13197`

---

## Step 1: Create PostgreSQL Database

1.  **Databases** -> **Create** -> **PostgreSQL**
2.  **Name**: `fidden-db`
3.  **Copy Internal URL**: `postgresql://fidden:PASS@dokploy-postgres-fidden-db:5432/fidden_prod`

*(Note: No need to create Redis, we will use your Cloud URL)*

---

## Step 2: Deploy Backend (Web Server)

1.  **Projects** -> **Create Service** -> **Application**
2.  **Name**: `fidden-web`
3.  **Source**:
    *   **Repository**: `fidden-server`
    *   **Branch**: `main`
    *   **Build Type**: `Dockerfile`
    *   **Docker Context**: `.`
4.  **Environment**:
    *   Add all variables from your `.env`.
    *   **DATABASE_URL**: Use the PostgreSQL Internal URL (from Step 1).
    *   **REDIS_URL**: Use your Redis Cloud URL.
    *   **CELERY_BROKER_URL**: Use your Redis Cloud URL.
    *   **CELERY_RESULT_BACKEND**: Use your Redis Cloud URL.
5.  **Network**:
    *   **Internal Port**: `8090`
6.  **Domain**:
    *   Add your domain (e.g., `api.fidden.com`) -> Port `8090` -> Enable SSL.
7.  **Deploy**.

---

## Step 3: Deploy Celery Worker

1.  **Projects** -> **Create Service** -> **Application**
2.  **Name**: `fidden-worker`
3.  **Source**:
    *   **Repository**: `fidden-server`
    *   **Branch**: `main`
    *   **Build Type**: `Dockerfile`
4.  **Environment**:
    *   Copy **ALL** variables from the Backend service.
5.  **Command / Entrypoint**:
    *   Go to **Deploy** (or Settings) -> **Docker Command**.
    *   Set **Command** to:
        ```bash
        celery -A fidden worker -l info
        ```
6.  **Network**:
    *   No domain needed.
7.  **Deploy**.

---

## Step 4: Deploy Celery Beat

1.  **Projects** -> **Create Service** -> **Application**
2.  **Name**: `fidden-beat`
3.  **Source**:
    *   **Repository**: `fidden-server`
    *   **Branch**: `main`
    *   **Build Type**: `Dockerfile`
4.  **Environment**:
    *   Copy **ALL** variables from the Backend service.
5.  **Command / Entrypoint**:
    *   Go to **Deploy** (or Settings) -> **Docker Command**.
    *   Set **Command** to:
        ```bash
        celery -A fidden beat -l info
        ```
6.  **Network**:
    *   No domain needed.
7.  **Deploy**.
