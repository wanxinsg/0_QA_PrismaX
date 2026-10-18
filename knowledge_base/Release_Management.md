# PrismaX Release Management and Process Optimization

> Document status: Proposal
>
> Applicable repositories: `app-prismax-rp` (frontend) and `app-prismax-rp-backend` (backend)
>
> Team size: 2 Developers and 1 QA; QA serves as the Production Approver
>
> Last updated: July 15, 2026

## 1. Objectives

This proposal is not limited to deciding who clicks **Deploy**. Its purpose is to establish a traceable, enforceable, and reversible production release pipeline:

1. Developers must not push directly to `main` or bypass approval to deploy to Production.
2. Only code that has passed Beta validation and is explicitly included in the current release scope may enter `main`.
3. Merging code into `main` must not automatically deploy it to Production. QA approval of the production build is still required.
4. Every release must clearly identify the included requirements, frontend and backend commits, image versions, approver, deployment time, and rollback procedure.
5. The process must remain lightweight and efficient for a small team without introducing unnecessary long-term maintenance overhead.

## 2. Current Process and Repository Findings

### 2.1 Current Known Process

```text
feature branch
    ↓ Developer merges
testing
    ↓ Automatic/manual deployment
Beta environment
    ↓ QA validation
main
    ↓ Developer deploys
Production environment
```

The main gap is that QA's Beta test result is not an enforced release gate. Developers may still be able to update `main` or trigger a Production deployment directly.

### 2.2 Local Repository Findings as of July 15, 2026

| Check | `app-prismax-rp` | `app-prismax-rp-backend` | Risk / Notes |
| --- | --- | --- | --- |
| `origin/main` | `bda1835` | `1863296` | The repositories are released independently, so both SHAs must be recorded. |
| `origin/testing` | 1 commit ahead of `main` | Diverged from `main`: 8 commits unique to `main`, 43 unique to `testing` | Backend `testing` must not overwrite or be fast-forwarded to `main` without review. |
| CI/CD file | `cloudbuild.yaml` | `cloudbuild.yaml` | No GitHub Actions workflow exists in either repository. |
| Frontend image | Fixed tag: `gcr.io/thepinai/app-prismax-rp` | — | Later builds overwrite the tag, making the Production commit difficult to identify. |
| Backend image | Produces both `$COMMIT_SHA` and `latest`; deploys `$COMMIT_SHA` | Builds and deploys 6 Cloud Run services together | Traceability is better, but a small change redeploys all 6 services and increases regression scope. |
| Deployment platform | Google Cloud Build + Cloud Run | Google Cloud Build + Cloud Run | Reuse Cloud Build approval instead of migrating CI/CD platforms initially. |
| Historical update indicators | Local remote reflog recorded an `origin/main` forced update on July 14, 2026 | Forced updates recorded on June 1 and June 21, 2026 | Force pushes to `main` must be blocked. |

The repositories expose only `cloudbuild.yaml`; they do not show Google Cloud Console trigger conditions, substitutions, approval settings, or IAM configuration. Local files also cannot confirm the current GitHub Ruleset or Branch Protection settings. Therefore, all remote settings must be verified against Section 13 rather than assumed from repository contents.

### 2.3 Risks in the Current `cloudbuild.yaml` Files

1. The frontend image has no `$COMMIT_SHA`, version, or digest identifier. A later build may cause the same image name to point to different content.
2. The backend deploys by `$COMMIT_SHA` but also publishes the mutable `latest` tag. Production records must use a commit tag or digest, never `latest`.
3. Build and deployment are combined in one Cloud Build configuration, preventing the exact artifact validated in Beta from being promoted naturally to Production.
4. A backend build deploys User Management, Teleop, Data Pipeline, Data Worker, Hex, and Forum together. Any small change can unnecessarily broaden the deployment and regression scope.
5. Frontend Cloud Run is in `us-west2`, while backend services are in `us-west1`. This may be intentional, but rollback commands and monitoring must use each service's actual region.
6. Protecting `main` does not prevent a user with sufficient GCP permissions from bypassing GitHub and deploying directly. Access control is required on both GitHub and GCP.

## 3. Comparison of Common Release Models

| Model | Core Approach | Advantages | Disadvantages | PrismaX Fit |
| --- | --- | --- | --- | --- |
| GitHub Flow | Short-lived feature branches merged through PRs and continuously deployed | Simple and fast | If `main` deploys automatically, strong testing gates and automation are required | Partially suitable: retain short branches and PRs, but require approval for Production. |
| Git Flow | Long-lived `develop`, `release`, `hotfix`, and `main` branches | Clear release boundaries | More branches and merge overhead; long-lived divergence | Full Git Flow is not recommended for this small team. |
| Trunk-Based + Feature Flags | Frequent mainline integration with incomplete features hidden by flags | Reduces branch divergence | Requires mature CI, monitoring, and feature-flag governance | A good long-term direction, but not a Phase 1 prerequisite. |
| Release Branch | Create a short-lived `release/*` branch from a stable baseline and include only approved changes | Supports selective releases | Requires cherry-pick management and repeated validation | Suitable when `testing` contains multiple requirements with different readiness states. |
| Environment Approval | A designated approver must authorize the deployment job | Enforces an auditable Production gate | Requires correct CI/CD permissions and bypass prevention | Strongly recommended, with QA as Production Approver. |

Recommended lightweight hybrid model:

```text
GitHub Flow short-lived feature branches
        +
testing / Beta integration validation
        +
short-lived release branches when needed
        +
main Release PR approval
        +
Cloud Build Production approval
```

References:

- [GitHub Flow](https://docs.github.com/en/get-started/using-github/github-flow)
- [About protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
- [Available rules for GitHub Rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets)
- [Cloud Build manual approval](https://cloud.google.com/build/docs/securing-builds/gate-builds-on-approval)
- [Cloud Run rollbacks and traffic migration](https://cloud.google.com/run/docs/rollouts-rollbacks-traffic-migration)

## 4. Recommended Target Process

### 4.1 End-to-End Flow

```text
Dev: feature/PRIS-xxx
        │
        │ PR + CI + Dev review
        ▼
testing ───────────────► Automatic Beta deployment
                              │
                              │ QA functional/regression testing
                              ▼
                      QA marks Ready for Release
                              │
        ┌─────────────────────┴─────────────────────┐
        │ Release everything                        │ Release selected items only
        ▼                                           ▼
testing → main Release PR             main → release/<version>
                                            Cherry-pick approved commits
                                            Deploy to Beta-RC and retest
        └─────────────────────┬─────────────────────┘
                              │ QA approves Release PR
                              ▼
                            main
                              │ Create protected version tag
                              ▼
                   Production Cloud Build Pending
                              │
                              │ QA approves deployment
                              ▼
                         Production
                              │
                              ▼
                     QA smoke test + monitoring
```

### 4.2 Meaning of the Two QA Gates

| Gate | QA Approval Target | QA Verifies | Result of Approval |
| --- | --- | --- | --- |
| Gate 1: Release PR | Code and release list in `testing/release → main` | Release scope, test results, known issues, migrations/configuration, and rollback plan | Code may enter `main`, but is not yet live. |
| Gate 2: Production Build | Cloud Build for a specific tag/SHA | Tag/SHA matches test evidence, release window is correct, and monitoring/rollback owners are available | Cloud Build may deploy to Production. |

Both gates are required. PR approval protects the production code branch; Cloud Build approval protects the production environment. Either gate alone leaves a bypass path.

## 5. Branch and Environment Rules

| Branch / Tag | Purpose | Environment | Who May Create or Update It | Lifecycle |
| --- | --- | --- | --- | --- |
| `feature/PRIS-xxx-description` | Development of one requirement | None or temporary Preview | Developer | Delete after merge. |
| `hotfix/PRIS-xxx-description` | Emergency Production fix | Beta-RC, then Production | Developer | Delete after release. |
| `testing` | Multi-requirement integration testing | Beta | PR merges only | Long-lived. |
| `release/YYYY.MM.DD.N` | Candidate containing selected requirements | Beta-RC | PRs/approved cherry-picks only | Delete shortly after release. |
| `main` | Current production code baseline | A normal push must not deploy | Release/Hotfix PR only | Long-lived and strongly protected. |
| `vYYYY.MM.DD.N` | Immutable release version | Production | Created by Release Owner; deployment approved by QA | Permanent and immutable. |

### 5.1 Default Path: `testing → main`

Use this path only when:

- All unreleased requirements in `testing` have passed QA.
- No feature needs to be deferred.
- Frontend/backend compatibility and configuration have been validated together.
- The Release PR diff matches the release list.

### 5.2 Selective Release Path: `release/*`

When `testing` contains unfinished, failed, or deferred requirements:

1. Create `release/YYYY.MM.DD.N` from the latest `origin/main`.
2. Cherry-pick only the independent commits approved by QA.
3. Deploy the release branch to Beta-RC; do not assume the cherry-picked result is identical to the original Beta build.
4. QA retests the included requirements, core smoke coverage, and frontend/backend compatibility in Beta-RC.
5. Open a `release/* → main` PR for QA approval.

Feature PRs should use squash merge into `testing`, preserving the PRIS ID in the commit title. This keeps one requirement identifiable as one commit and makes selective release safer. Do not cherry-pick unchecked merge commits.

## 6. Standard Release SOP

### Phase A: Development and Beta Entry

1. Create `feature/PRIS-xxx-description` from the latest `testing`.
2. Open a `feature → testing` PR containing the requirement link, affected modules, test method, configuration/database changes, and rollback notes.
3. Require review by at least one other Developer and passing CI before merge.
4. Use squash merge and preserve the PRIS ID in the commit title.
5. Automatically deploy `testing` to Beta through Cloud Build; QA approval is not required for Beta.
6. The Developer performs basic Beta self-testing before handing the build to QA.

### Phase B: QA Validation and Admission

QA records the following for each requirement:

- Beta build ID.
- Frontend commit SHA and backend commit SHA.
- Requirement test result.
- Regression results for affected modules.
- Open issues and their severity.
- Decision: `Ready for Release` or `Blocked`.

Do not mark a requirement `Ready for Release` when:

- An unaccepted P0/P1 defect remains open.
- Required Production configuration differs from the test environment and has not been validated.
- A database migration lacks a compatibility or rollback plan.
- The frontend/backend SHAs actually tested cannot be identified.
- No executable post-release smoke test or rollback method exists.

### Phase C: Form the Release Candidate

1. PM confirms the business scope and release window; QA confirms test admission.
2. The Developer creates one Release Manifest with exact SHAs for both repositories. If one repository is unchanged, record `No change` and its current Production SHA.
3. If all content in `testing` is releasable, open a `testing → main` Release PR. Otherwise, create a `release/*` branch and deploy it to Beta-RC.
4. Freeze the Release PR scope. Any code change invalidates the previous QA approval and requires another review.
5. Open separate frontend and backend Release PRs, cross-link them, and use the same version number.

### Phase D: QA Approval of the Release PR

QA verifies, in order:

1. The diff contains only items in the release list.
2. All required checks pass.
3. Frontend/backend APIs, configuration, and deployment order are compatible.
4. The Beta/Beta-RC SHAs match the Release Candidate.
5. Known issues are accepted by PM and rollback conditions and owners are clear.
6. Approve when all conditions pass; otherwise request changes. Verbal consent is not a substitute for GitHub approval.

Merging into `main` means the code is eligible for release; it must not deploy automatically.

### Phase E: Version Creation and Production Deployment Request

1. The Release Owner creates an annotated tag on the merged `main` commit, for example `v2026.07.15.1`.
2. Both repositories use the same version number while the Release Manifest records their different commit SHAs.
3. The Production trigger accepts only tags matching `^v[0-9]{4}\.[0-9]{2}\.[0-9]{2}\.[0-9]+$`.
4. Enable **Require approval before build executes**. The build must remain Pending and must not start deployment.
5. The Developer gives QA the Build ID, tag, SHA, planned time, and rollback version.

### Phase F: QA Approval of the Production Build

QA checks in Google Cloud Build that:

- Repository, tag, and commit SHA match the Release Manifest.
- The Production trigger and Production service account are used.
- Frontend/backend deployment order is correct.
- No other Production deployment is running.
- Release window, monitoring owner, and rollback owner are ready.

QA then approves or rejects the build with a reason. QA does not run deployment commands; Cloud Build's service account performs the deployment.

### Phase G: Post-Deployment Validation and Closure

1. Developers monitor the build, Cloud Run revisions, error logs, and key metrics.
2. QA executes the Production smoke test.
3. After frontend and backend succeed and smoke tests pass, QA marks the release `Released`.
4. Record the actual deployment time, Cloud Build ID, Cloud Run revision, image digest, and smoke result.
5. If a rollback condition occurs during the observation period, follow Section 10 immediately.

## 7. Coordinated Frontend and Backend Release Rules

The repositories are separate, but users receive one product release. Maintain one Release Manifest:

| Field | Example |
| --- | --- |
| Release Version | `v2026.07.15.1` |
| Frontend SHA | `app-prismax-rp@<40-character-SHA>` |
| Backend SHA | `app-prismax-rp-backend@<40-character-SHA>` |
| Frontend Image Digest | `sha256:<digest>` |
| Backend Image Digests | One `sha256:<digest>` per service |
| Included PRIS Items | `PRIS-xxx, PRIS-yyy` |
| Configuration / Migration | Yes/No and execution order |
| Rollback Version | Previous stable Release Manifest |
| QA Approver | GitHub/GCP username |

Choose deployment order based on compatibility:

- If the backend is backward compatible, deploy it first, validate the API, then deploy the frontend.
- If the frontend requires a new backend field, deploy the backend first.
- For breaking API changes, use expand-and-contract: support old and new clients first, then remove the old API in a later release.
- If only one repository changes, record `No change` for the other; never leave it blank.

## 8. Artifact and Cloud Build Improvements

### 8.1 Phase 1: Minimum Changes

1. Keep Google Cloud Build and Cloud Run.
2. Use separate Beta and Production triggers, service accounts, and substitutions.
3. The Beta trigger listens to `testing`, requires no manual approval, and can deploy only Beta services.
4. The Production trigger listens only to protected release tags, requires manual approval, and can deploy only Production services.
5. Grant QA `roles/cloudbuild.builds.approver`; do not grant it to Developers.
6. Developers must not be able to modify the Production trigger, impersonate its service account, or update Production Cloud Run services directly.
7. Add `$COMMIT_SHA` to frontend image tags immediately; Production must not deploy an unversioned tag.

### 8.2 Phase 2: Build Once and Promote the Same Artifact

Split the current build-and-deploy configuration:

```text
build.yaml
  └─ Test, build image, push commit SHA, and output digest

deploy-beta.yaml
  └─ Deploy that digest to Beta

deploy-prod.yaml
  └─ After QA approval, deploy the same digest to Production
```

Production should use the exact image digest validated in Beta-RC instead of rebuilding a theoretically identical artifact after approval. A digest is immutable and should be the primary identifier in release records. `latest` may be retained for development convenience but must never identify a Production release.

Reference: [Artifact Registry image names and digests](https://cloud.google.com/artifact-registry/docs/docker/names).

### 8.3 Backend Six-Service Optimization

Continue unified deployment in the short term, but record all six revisions in the Release Manifest. In the medium term:

1. Trigger builds by changed path; for example, a change under `app_prismax_hex/**` should not rebuild Teleop.
2. Give each service an independent image SHA/digest and deployment step.
3. Mark which services actually changed and were deployed.
4. Run a full build and expanded regression only when shared dependencies or `cloudbuild.yaml` change.

## 9. GitHub Protection Rules

Configure consistent Rulesets in both repositories. Prefer Rulesets; equivalent Branch Protection may be used where necessary.

### 9.1 Required Rules for `main`

- Require a pull request before merging.
- Require 1 approval.
- Require review from Code Owners; designate QA/Release Approver through `CODEOWNERS`.
- Dismiss stale approvals when new commits are pushed.
- Require approval of the most recent reviewable push.
- Require passing status checks, including build, unit test, and lint/static analysis; add E2E later.
- Require conversation resolution before merging.
- Block force pushes.
- Restrict deletions.
- Do not allow routine administrator bypass.
- Restrict direct pushes; normal updates must use GitHub PR merge.

Example `CODEOWNERS`:

```text
* @PrismaXAI/release-approvers
/.github/ @PrismaXAI/release-approvers
/cloudbuild.yaml @PrismaXAI/release-approvers
```

One required approval only guarantees that someone approved; it does not guarantee QA approval. Combine it with Code Owners, designated reviewers, or a release Ruleset. Cloud Build approval remains the final environment gate.

### 9.2 Recommended Rules for `testing`

- Require a PR before merging.
- Require review by at least one other Developer; QA need not code-review every feature.
- Require passing status checks.
- Block force pushes and restrict deletion.
- Allow rapid iteration but never bypass CI through direct pushes.

### 9.3 Tag Protection

- Create a Tag Ruleset matching `v*`.
- Prevent existing release tags from being moved, updated, or deleted.
- Allow only the Release Owner to create tags.
- Ensure the Production trigger resolves and records the complete commit SHA.

## 10. Rollback and Hotfix

### 10.1 Rollback Conditions

Developers or QA may initiate rollback without waiting for normal release approval when any condition is met:

- A core page or API is unavailable.
- A P0/P1 issue affects login, payment, upload, Teleop, or data processing.
- Error rate, latency, or resource usage significantly exceeds its threshold.
- Data corruption, privilege escalation, security, or privacy risk occurs.
- The issue cannot be diagnosed or fixed within the agreed observation period.

### 10.2 Cloud Run Rollback

Prefer shifting traffic to the last known stable revision instead of rebuilding old code:

```bash
gcloud run services update-traffic <SERVICE> \
  --to-revisions <LAST_STABLE_REVISION>=100 \
  --region <SERVICE_REGION>
```

Do not automatically roll back all six backend services. Use the Release Manifest and dependency relationships to identify affected services. If a database migration is irreversible, application rollback alone may worsen the incident; migrations must be backward compatible.

After rollback:

1. QA runs the core smoke test.
2. Set the release status to `Rolled Back` and record the reason, revision, and time.
3. Create a defect/incident record and do not move the original release tag.
4. Release the fix through the Hotfix process under a new version.

### 10.3 Hotfix Process

```text
main → hotfix/PRIS-xxx
     → Dev review + CI
     → Beta-RC validation
     → hotfix → main PR (QA approval)
     → new tag
     → Production build (QA approval)
```

Emergency does not mean unaudited. Break-glass is permitted only when platform failure prevents the normal approval system from operating. PM/owner confirmation is required, and all PR, build, reason, and postmortem records must be completed within one business day.

## 11. Roles and Responsibilities (RACI)

| Activity | Developer | QA / Production Approver | PM | Repository/GCP Admin |
| --- | --- | --- | --- | --- |
| Development, self-test, PR | R/A | I | I | I |
| Code review | R | C | I | I |
| Beta deployment maintenance | R | I | I | C |
| Beta functional/regression testing | C | R/A | I | I |
| Business scope and release window | C | C | R/A | I |
| Release Manifest | R | A | C | I |
| Release PR approval | C | R/A | I | I |
| Trigger Production build | R | I | I | I |
| Approve Production build | I | R/A | I | C |
| Deployment monitoring and technical rollback | R | C | I | C |
| Production smoke test | C | R/A | I | I |
| Ruleset, trigger, and IAM maintenance | I | C | I | R/A |

`R` = Responsible, `A` = Accountable, `C` = Consulted, `I` = Informed.

### Single-QA Availability Risk

- Normal releases may be approved only by QA.
- For planned leave, assign one trained Backup Approver with explicit start and end dates.
- Developers may perform an emergency traffic rollback but must notify QA/PM and complete the records.
- QA must not approve a Production deployment that QA initiated. A Developer triggers it; QA approves it.

## 12. Release Checklist Templates

### 12.1 Before Release

- [ ] Version and release time confirmed.
- [ ] Release Manifest contains complete frontend/backend SHAs.
- [ ] Included PRIS items match the Release PR diff.
- [ ] All requirements are `Ready for Release`.
- [ ] All required checks pass.
- [ ] Beta-RC functional and affected-area regression testing passes.
- [ ] Frontend/backend compatibility is verified.
- [ ] Environment variables, secrets, and Cloud Build substitutions are verified.
- [ ] Database migration is backward compatible and has a recovery/compensation plan.
- [ ] Previous stable Cloud Run revision and image digest are recorded.
- [ ] Monitoring and rollback owners are available.
- [ ] QA approved the Release PR.

### 12.2 Before Production Approval

- [ ] Build corresponds to a protected release tag.
- [ ] Tag points to the `main` SHA in the Release Manifest.
- [ ] Production build is Pending and has not deployed.
- [ ] Trigger, service account, region, and service names are Production configuration.
- [ ] No concurrent Production deployment exists.
- [ ] Release window is correct.
- [ ] QA approval is recorded in Cloud Build.

### 12.3 Post-Release Smoke Test

- [ ] Frontend home page, login, and primary navigation work.
- [ ] Frontend assets and API host point to Production.
- [ ] Core API health checks pass.
- [ ] Core upload/data-processing flow works.
- [ ] Teleop core flow works when affected or shared dependencies changed.
- [ ] Hex core flow works when affected or shared dependencies changed.
- [ ] Forum core flow works when affected or shared dependencies changed.
- [ ] Error logs, 5xx rate, latency, and instance health show no abnormality.
- [ ] Cloud Run revision, image digest, and Build ID are recorded.
- [ ] Release status is updated to `Released`.

## 13. One-Time Implementation Checklist

### 13.1 Both GitHub Repositories

- [ ] Confirm repository visibility and GitHub plan.
- [ ] Create a strong Ruleset for `main`.
- [ ] Create a baseline Ruleset for `testing`.
- [ ] Create an immutable Tag Ruleset for `v*`.
- [ ] Create a `release-approvers` team and add QA.
- [ ] Add `CODEOWNERS`.
- [ ] Configure PR and Release PR templates.
- [ ] Disable routine administrator bypass.
- [ ] Verify direct and force pushes to `main` are rejected.

### 13.2 Google Cloud Build

- [ ] List existing frontend/backend Beta and Production triggers.
- [ ] Verify branch/tag regex, configuration file, substitutions, and service account for each trigger.
- [ ] Ensure the Beta trigger can deploy only Beta services.
- [ ] Ensure the Production trigger accepts only protected release tags.
- [ ] Enable **Require approval** on the Production trigger.
- [ ] Grant QA the Cloud Build Approver role.
- [ ] Ensure Developers do not have the Cloud Build Approver role.
- [ ] Prevent Developers from modifying the Production trigger or directly deploying Production Cloud Run services.
- [ ] Give the Production service account only the minimum permissions required for its services.
- [ ] Verify a rejected build executes no deployment step.
- [ ] Verify approval records contain approver, time, and comment/Release URL.

### 13.3 Current Branch Baseline Governance

Before enabling the process:

1. Determine whether the frontend commit present in `origin/testing` but not `origin/main` should be released.
2. Audit the backend's 8/43 unique commits in `origin/main...origin/testing` against the intended release scope.
3. Do not align remote branches through force push or `reset --hard` followed by force push.
4. Use an explicit Baseline Release PR to preserve required changes, resolve conflicts, and run full regression testing.
5. After stabilizing the baseline, require every new change to flow through PRs so divergence does not continue growing.

## 14. Optional GitHub Environment Approach

If the GitHub plan and repository visibility support Environment Required Reviewers for private repositories, GitHub Actions may use `environment: production`, with QA as Required Reviewer, Prevent self-review enabled, and deployment restricted to protected tags.

However, GitHub currently states that Required Reviewers on Free, Pro, and Team plans are available only for public repositories. If PrismaX is private and its plan does not support this feature, Cloud Build **Require Approval** must remain the actual Production gate. Do not assume GitHub Environments are available.

Reference: [GitHub deployments and environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments).

## 15. Phased Implementation Plan

### P0: Immediate (1–2 Days)

1. Protect `main`, `testing`, and release tags in both repositories; block direct and force pushes.
2. Enable manual approval on Production Cloud Build triggers, grant QA the Approver role, and remove it from Developers.
3. Establish the Release Manifest, Release PR, and checklist.
4. Add commit SHA tags to frontend images.
5. Audit the current frontend/backend branch divergence and establish a baseline.

### P1: Within One Week

1. Add complete required CI checks for frontend and backend.
2. Separate Beta/Production triggers and service-account permissions.
3. Establish automated or semi-automated Production smoke testing.
4. Rehearse one rejection and one Cloud Run rollback.

### P2: Future Improvements

1. Build once and promote the image digest from Beta-RC to Production.
2. Build and deploy the six backend services selectively by path and dependency.
3. Introduce gradual traffic rollout, automatic error-rate evaluation, and automatic rollback.
4. Introduce Feature Flags for unfinished capabilities and reduce long-term `testing` divergence.

## 16. Acceptance Criteria

The process must be exercised in practice; reviewing configuration pages alone is insufficient:

1. A Developer's direct push and force push to `main` both fail.
2. A Release PR cannot merge into `main` without QA approval.
3. Adding a commit to an approved PR dismisses the previous approval.
4. A normal update to `main` does not deploy to Production.
5. A Production build remains Pending without QA approval, and rejection prevents deployment.
6. Developers cannot approve their own Production build or bypass the trigger to deploy directly.
7. A completed release can be traced through the Release Manifest to frontend/backend commits and all six backend service revisions/digests.
8. One service can be rolled back to its previous stable Cloud Run revision within the agreed time and pass smoke testing.

Only after all eight criteria pass can QA's role as Production Approver be considered technically enforceable and auditable rather than merely procedural.

## 17. Jira Ticket

### Title

Implement QA-Gated Production Release Process

### Description

Improve the PrismaX release process for both frontend and backend repositories to ensure that only QA-verified changes can be released to Production.

### Requirements

- Protect `main` and `testing`: require PR approval and CI checks; block direct and force pushes.
- Automatically deploy `testing` to Beta for QA verification.
- Require QA approval before merging a Release PR into `main`.
- Trigger Production deployment only from a protected version tag.
- Enable manual QA approval for Production builds in Google Cloud Build.
- Tag frontend and backend images with the commit SHA and record the deployed SHA/image digest for traceability and rollback.
- Ensure Developers cannot bypass approval or deploy directly to Production.

### Acceptance Criteria

A Production deployment cannot start without QA approval, and each release can be traced to its frontend/backend commits, image digests, approver, and previous stable version.
