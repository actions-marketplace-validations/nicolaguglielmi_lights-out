# infra

Terraform for L2 (GCP) and L3 arrives at M8. Nothing here runs today.

## Before you `terraform apply`

Everything below is optional: L0 and L1 are the whole product and need no
GCP account (ADR 0022). L2 replaces the local containers with managed
services; it adds no capability.

**Cloud SQL is the one fixed cost.** Every other L2 service (Cloud Run,
Cloud Deploy, Pub/Sub, Firestore, Artifact Registry, Managed Prometheus)
bills on use and idles at zero. Cloud SQL bills per instance-hour while
the instance is running, whether or not anything connects. Between test
runs, stop or delete it:

```sh
./go down PROFILE=l2                       # stops the instance (M8)
gcloud sql instances patch <name> --activation-policy NEVER   # stop by hand
gcloud sql instances delete <name>         # or delete it; terraform apply recreates it
```

Locally the database is a Postgres container and this problem does not
exist.
