# Terraform GPU Inference IaC Scaffold

This directory contains a **demonstration Infrastructure as Code (IaC) scaffold** for how a GPU inference API service could be modeled for deployment in Google Cloud.

It is intentionally minimal and intended for planning/review workflows only.

## Included

- `main.tf`: Example Google provider configuration and Cloud Run v2 service resource structure.
- `variables.tf`: Basic variable declarations for project and region.

## Usage

```bash
terraform init
terraform plan
```

> This scaffold is for demonstration only and should be adapted before any real infrastructure provisioning.
