---
title: "PrismaX Release Management Optimization Requirements"
subtitle: "Short Product Requirements Document"
date: "July 17, 2026"
lang: en-US
---

## 1. Document Overview

**Status:** Proposal  
**Scope:** Frontend `app-prismax-rp`, backend `app-prismax-rp-backend`, and gateway `gateway-prismax-rp`  

This document defines a lightweight, traceable, and reversible Production release process for PrismaX, delivered in two phases:

- **Phase 1** — QA must approve the Release PR before code enters `main`; merging into `main` must not automatically deploy to Production.
- **Phase 2** — Adds a second, separate QA approval gate before the Production build may deploy.

## 2. Principles

1. Developers must not push or force-push directly to `main`.
2. Only code that has passed Beta validation and is within the approved release scope may enter `main`.
3. Two sequential QA gates control every release — a Release PR gate before `main` (Phase 1, §5) and a Production build gate before deployment (Phase 2, §6).
4. Every release must be fully traceable: frontend/backend/gateway SHAs, image versions or digests, release scope, QA approvals, deployment time, and rollback version (see §8).
5. Reuse existing Google Cloud Build and Cloud Run; avoid unnecessary platform migration or maintenance overhead.

## 3. Branch and Version Management

- Development branch: `feature/PRIS-xxx-description`, created from `testing` and merged through a pull request.
- Integration branch: `testing`, automatically deployed to Beta and updated only through pull requests.
- Selective release: when `testing` contains incomplete work, create `release/YYYY.MM.DD.N` from `main`, include only approved commits, deploy the release branch to the existing Beta environment, and retest the exact release candidate before merging it into `main`.
- Production baseline: `main`, updated only through Release or Hotfix pull requests and never deployed by an ordinary branch update.
- Release tag: `vYYYY.MM.DD.N`, protected against movement, modification, and deletion.
- Feature pull requests should use squash merge and retain the PRIS ID in the commit title.

## 4. End-to-End Flow

```text
Dev: feature/PRIS-xxx
  |
  | PR + CI + Developer review
  v
testing -> Automatic Beta deployment
  |
  | Developer self-test + QA functional/regression test
  v
QA marks Ready for Release
  |
  +-- Release all: testing -> main Release PR
  |
  +-- Release selected items only:
      main -> release/<version>
      -> include approved commits only
      -> deploy to existing Beta and retest
      -> release/* -> main Release PR
  |
  | Phase 1: QA approves the exact Release PR scope
  v
main
  |
  | Merge does not deploy; create protected version tag
  v
Developer triggers Production build
  |
  | Phase 1: deploys without a Cloud Build QA gate
  | Phase 2: remains Pending until QA approval
  v
Production
  |
  v
QA smoke test + monitoring
```

The Phase 1 Release PR approval controls which code may enter `main`. The Phase 2 Production Build approval is a separate environment gate that controls whether the exact tagged release may deploy.

## 5. Phase 1 — Release PR Gate

**Requirement:** Code may enter `main` only through a QA-approved Release PR. Merging the approved PR makes the code release-eligible but must not automatically deploy it to Production.

**Controls**

- A `testing → main` or `release/* → main` Release PR must be explicitly approved by QA before merge.
- QA verifies the release scope, test evidence, known issues, frontend/backend/gateway compatibility, configuration or migrations, and rollback plan.
- Any new commit or scope change dismisses the previous QA approval and requires another review.
- Required CI checks must pass and all review conversations must be resolved before merge.
- A merge into `main` updates the Production code baseline only and must not start a Production build or Cloud Run deployment.
- Production deployment uses a dedicated protected-tag Cloud Build trigger, separate from the `main` merge pipeline, and is started explicitly by a Developer — Phase 1 does not require QA approval inside Cloud Build itself.

**Workflow**

1. A Developer submits a `feature → testing` PR and completes code review and CI.
2. `testing` deploys automatically to Beta. The Developer self-tests before QA performs functional and regression testing.
3. The Developer provides the exact frontend, backend, and gateway SHAs deployed to Beta. QA verifies the release information and marks the requirement as `Ready for Release` or `Blocked`.
4. The Developer creates one Release Manifest and opens `testing → main`. When only selected items are releasable, the Developer creates `release/*`, deploys it to the existing Beta environment for QA retesting, and then opens `release/* → main`.
5. QA approves the exact Release PR scope. The Release Owner then merges the PR and creates the protected version tag.
6. The Developer explicitly triggers the Production build for the specified tag and SHA; merging into `main` does not trigger it.
7. Developers monitor the deployment, and QA completes the Production smoke test.

**Exit criteria:** Code cannot enter `main` without recorded QA approval of the exact Release PR scope; new commits or scope changes dismiss the approval and block merge until QA approves again. After merge, `main` updates the Production code baseline only — no Production build or Cloud Run deployment starts until a Developer explicitly triggers the protected-tag pipeline.

## 6. Phase 2 — Production Deployment Gate

**Requirement:** Production deployment requires a second QA approval, separate from the Phase 1 Release PR approval.

**Controls**

- The Developer triggers the protected-tag Production build, but the build remains Pending.
- QA verifies the Release Manifest, repository, tag, full SHA, image digest, Production trigger, service account, release window, monitoring owner, and rollback readiness.
- QA approves or rejects the Production build with a recorded reason. QA does not run deployment commands — the Production Cloud Build service account performs the deployment.
- Developers must not hold the Cloud Build Approver role or bypass the gate by modifying the Production trigger, impersonating its service account, or directly updating Production Cloud Run services.
- Any unapproved or rejected build must execute no deployment step.

**Workflow**

1. The Phase 1 development, Beta validation, Release Manifest, Release PR approval, merge, and version-tag steps remain unchanged.
2. The Developer triggers the Production build for the approved release tag.
3. Cloud Build remains Pending until QA approves or rejects the exact tag and SHA.
4. After approval, the Production service account deploys the release.
5. Developers monitor the deployment, and QA completes the Production smoke test and closes the release.

**Exit criteria:** A Developer can request a Production deployment but cannot authorize it — an unapproved or rejected build stays Pending and executes no deployment step. Only QA approval allows the Production service account to deploy the specified release.

**Cross-phase criteria:** Every release must be traceable end-to-end through the Release Manifest (exact SHAs, image digests, approval records, Cloud Run revisions), the defined smoke test must be completed after deployment, and the release must be quickly revertible to the recorded stable revision when required.

## 7. Permissions and Platform Configuration

### 7.1 GitHub

- `main` and `testing` are updated only through pull requests; direct pushes, force pushes, and deletion are blocked.
- `main` requires at least one approval, enforced via `CODEOWNERS` or a designated approval group so a Release PR cannot merge without QA sign-off (per §5 Controls).
- A Tag Ruleset protects `v*`; only the Release Owner may create release tags.

### 7.2 Google Cloud

- Beta and Production use separate triggers, service accounts, and permissions.
- Phase 1: the Beta trigger deploys only Beta; the Production trigger accepts only protected release tags and is started explicitly by a Developer.
- Phase 2: enable **Require approval** on the Production trigger and grant QA `roles/cloudbuild.builds.approver`; Developers must not hold this role (per §6 Controls).
- Frontend images must immediately include `$COMMIT_SHA`. Production records and deployments must never use `latest`.

## 8. Minimum Release Manifest Fields

Each product release must maintain one shared Release Manifest containing:

- Release version and planned window;
- Full frontend, backend, and gateway commit SHAs;
- For every in-scope repository that is unchanged, record `No change` and its current Production SHA;
- Frontend image digest, the image digest for each backend service, and the gateway image digest;
- Included PRIS items;
- Configuration changes, database migrations, and execution order;
- Previous stable version, Cloud Run revision, and rollback owner;
- Release PRs, Release PR QA approver, approval time, and Cloud Build IDs; in Phase 2, also record the Production build QA approver, decision, and approval time;
- Actual deployment time, Production smoke-test result, and final status.

## 9. Rollback and Hotfix

- Initiate rollback for core page or API outages, P0/P1 issues, data or security risks, or severe abnormality in key metrics.
- Prefer shifting Cloud Run traffic to the previous stable revision instead of rebuilding old code.
- Roll back only the affected backend services rather than all six by default. Database migrations must remain backward compatible or include a compensation plan.
- After rollback, QA runs the core smoke test. Set the release status to `Rolled Back` and record the reason, revision, and time.
- A Hotfix still requires Developer review, CI, validation in the existing Beta environment, QA approval of the PR, and a new version tag. From Phase 2 onward, it also requires QA approval of the Production build.

## 10. Implementation Plan

### Phase 1 rollout tasks

- Protect `main`, `testing`, and `v*`; block direct and force pushes.
- Require QA approval for every `testing/release → main` Release PR through `CODEOWNERS`, a release-approver team, or an equivalent enforceable rule; dismiss stale approvals on any new commit.
- Require passing checks, resolved review conversations, verified release scope, and rollback information before merge.
- Separate the `main` merge pipeline from the Production deployment trigger; configure the Production trigger to accept only protected release tags and require an explicit Developer action.
- Establish the Release Manifest, Release PR template, release checklist, shared versioning, and cross-linking across frontend, backend, and gateway releases.
- Add commit SHA tags to frontend images and record immutable SHAs or digests for all Production deployments.
- Define how a release or hotfix branch is temporarily deployed to the existing Beta environment for QA validation, and establish the Production smoke-test checklist.
- Audit the current `main`/`testing` divergence in all three repositories and resolve it through a Baseline Release PR where required.

### Phase 2 rollout tasks

- Enable **Require approval** on every Production Cloud Build trigger.
- Grant QA `roles/cloudbuild.builds.approver` and ensure Developers do not hold this permission.
- Keep the build Pending until QA verifies the Release Manifest, tag, SHA, service account, deployment window, monitoring owner, and rollback owner.
- Prevent Developers from modifying the Production trigger, impersonating its service account, or directly updating Production Cloud Run services.
- Record the QA approver, approval time, decision, and release reference in the Release Manifest.
- Verify that rejected or unapproved builds execute no deployment step.
