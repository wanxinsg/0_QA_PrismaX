# Prismax User Management System — Operations Guide

> **Audience:** Operations, Support, and QA teams.
> This document describes the system's features and behaviors from an end-user and operational perspective. Internal implementation details are intentionally omitted.
>
> Last updated: 2026-05-15

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [User Identity & Login](#2-user-identity--login)
3. [Membership Tiers](#3-membership-tiers)
4. [User Roles](#4-user-roles)
5. [Account Linking (Email ↔ Wallet)](#5-account-linking-email--wallet)
6. [User Profile Management](#6-user-profile-management)
7. [Third-Party Account Binding](#7-third-party-account-binding)
8. [Payment & Membership Upgrade](#8-payment--membership-upgrade)
9. [Points System](#9-points-system)
10. [TeleOp Robot Access](#10-teleop-robot-access)
11. [Robot Reservation](#11-robot-reservation)
12. [Operator System](#12-operator-system)
13. [Referral Program — End-to-End Flow](#13-referral-program--end-to-end-flow)

---

## 1. System Overview

Prismax User Management handles all aspects of identity, access, and membership for the Prismax platform. It sits at the center of:

- **Who you are** — login via email or blockchain wallet (Solana, Ethereum, Base, Monad, Aptos).
- **What you can do** — determined by membership tier and functional role.
- **What you earn** — a points system tied to engagement and membership.
- **Data production** — an Operator program allowing robot owners to upload training data.

---

## 2. User Identity & Login

### Login Methods

| Method | How it works |
|--------|-------------|
| **Email (passwordless)** | User enters email → receives a 6-digit verification code (valid 10 min) → enters code to authenticate. |
| **Google / Apple OAuth** | Standard third-party OAuth redirect flow. |
| **Blockchain Wallet** | User connects a supported wallet. The system checks for an on-chain balance; if found, a user record is created automatically. |

### Supported Wallet Chains

Solana · Ethereum · Base · Monad · Aptos

### Session Token

After login, the server issues a long-lived `hash_code` token. All subsequent authenticated requests carry this token via the `Authorization: Bearer <token>` header. On logout, the server invalidates the token by rotating it.

### Anti-Bot Protections

- Email login requires passing **reCAPTCHA v3 and v2** checks.
- Emails from known bot-pattern addresses are silently dropped without sending a real email.
- A **30-second cooldown** prevents rapid re-sending of verification codes to the same address.
- Login attempts with a low reCAPTCHA score are rejected outright.

---

## 3. Membership Tiers

All users have a `user_class` that controls access to premium features and points multipliers.

| Tier | Price | Key Entitlements |
|------|-------|-----------------|
| **Explorer Member** | Free (default) | Basic platform access; TeleOp blocked; 10 pts/day login |
| **Amplifier Member** | $99 one-time | Limited TeleOp access (see §10); 30 pts/day login |
| **Innovator Member** | $399 one-time | Full TeleOp + Fast Track; robot reservations; 50 pts/day login |

Upgrades follow a one-directional path: **Explorer → Amplifier → Innovator**. There is no downgrade path. Buying a lower-tier product when already at a higher tier has no effect.

---

## 4. User Roles

In addition to membership tier, users may hold a **functional role** (`user_role`) that grants platform-specific capabilities. Roles are independent of membership tier.

| Role | How Assigned | What It Enables |
|------|-------------|-----------------|
| `operator` | Admin approval after application | Register robots, upload VLA training data |
| `qa` | Admin grants directly | QA data review tasks |
| `senior qa` | Admin grants directly | QA data review tasks (higher seniority) |
| `expert qa` | Admin grants directly | QA data review tasks (top seniority) |

A user may hold a membership tier and a role simultaneously (e.g., an Explorer-tier user can still be an `operator`).

---

## 5. Account Linking (Email ↔ Wallet)

A user may have both an email account and a wallet account. The system treats them as a **single identity** once linked.

### Linking behavior

- When a user accesses the platform with both an email and a wallet address, the system automatically creates a bidirectional link between the two accounts.
- After linking, the **email account is treated as the primary identity** and its profile data is returned.
- A high-tier wallet account (`Amplifier` or `Innovator`) **cannot be linked to a different email account** — this prevents tier-sharing abuse.

### Unlinking

Users can unlink their wallet from their email via the platform. Both sides of the link are cleared.

---

## 6. User Profile Management

Users can update their profile information from the account settings page. Editable fields include:

- Display name (nickname)
- Public / contact email address *(requires email verification code confirmation)*
- Telegram ID
- Phone number
- Twitter username

**Identity is always re-verified** before any profile update is saved. Token-based authentication ensures users can only edit their own profiles.

---

## 7. Third-Party Account Binding

### Twitter

- Users can connect their Twitter account via OAuth.
- Once connected, the Twitter username and ID are stored on the user record.
- Users can **unlink** their Twitter account at any time from the profile page.

### Discord

- Users can connect their Discord account via OAuth (same flow as Twitter).
- Once connected, the Discord username and ID are stored.
- Users can **unlink** their Discord account at any time.

> **Note for ops:** Both Twitter and Discord bindings use state tokens with expiry and signature checks to prevent session hijacking during the OAuth flow. If a user reports a failed binding, verify they did not log out mid-flow.

---

## 8. Payment & Membership Upgrade

### Payment Methods

| Method | Provider | Supported Assets |
|--------|----------|-----------------|
| Credit / Debit Card | Stripe | USD |
| Crypto | On-chain verification | SOL, ETH, BASE, MON, APT |

### Upgrade Prices

- Explorer → Amplifier: **$99**
- Amplifier → Innovator: **$399**

### How Upgrades Are Processed

**Stripe:** The platform creates a Stripe Checkout Session. After the user completes payment, Stripe sends a webhook to the server, which records the purchase and upgrades the membership tier automatically.

**Crypto:** The user submits their transaction hash. The server verifies the on-chain transfer (correct recipient address, correct amount within tolerance) before recording the payment and upgrading the tier.

> **Duplicate protection:** Each transaction hash can only be recorded once. Attempts to reuse a hash are rejected.

### Reconciliation

A payment verification system periodically cross-checks on-chain transactions and Stripe records against the `purchase_records` table, surfacing any missing or mismatched entries for manual review.

---

## 9. Points System

### Earning Points

| Source | Amount | Conditions |
|--------|--------|------------|
| **First-time initialization** | 1,000 pts (2,000 on Monad) | Triggered when a new user's points balance is zero |
| **Daily login** | Explorer: 10 / Amplifier: 30 / Innovator: 50 pts | Once per UTC calendar day; Monad chain earns double |
| **Quiz completion** | 500 pts per correct answer + 1,000 bonus if all correct | One-time only; cannot be resubmitted |
| **Referral invite bonus** | 500 pts per referred user | Paid out to the referrer when a new user joins via their code |
| **Referral revenue share** | 10% of all referred users' cumulative points | Incremental; settles automatically when the referrer checks their referral dashboard |
| ~~**Comment reward**~~ | ~~50 / 150 pts~~ | **Temporarily disabled** |

### Referral System

Each user has a unique referral code. When a new user registers with a referral code:
- The referrer earns a 500-point invite bonus per new user.
- The referrer continuously earns 10% of the referred users' total accumulated points (incremental, anti-double-count).

### Anti-Abuse

- reCAPTCHA checks on login and quiz submission.
- Bot-detection scans for transactions dated in the future or before the platform launch date.
- Suspicious accounts are flagged in the `detected_bot_users` table for review.

---

## 10. TeleOp Robot Access

TeleOp allows users to remotely control Prismax robots. Access is governed by **membership tier** and the **robot type** (`robot_class`).

### Robot Classes

| robot_class | Description | Example robots |
|-------------|-------------|----------------|
| `training` | General training arms | arm1, arm4 |
| `open` | Open-access buddy arms | arm3 |
| `access` | Invite-only / partner arms | arm2 (Monad-gated) |

### Access Rules by Tier

| Tier | `training` arm | `open` arm | `access` arm |
|------|---------------|-----------|-------------|
| **Explorer** | ❌ Blocked | ❌ Blocked | ❌ Blocked |
| **Amplifier** | ✅ Up to **3 queue joins per UTC day** | ✅ Up to **3 lifetime uses** | ✅ No extra cap (invite code + Monad wallet required) |
| **Innovator** | ✅ Unlimited | ✅ Unlimited | ✅ Unlimited |

### Fast Track (Innovator Only)

Innovator members can use **Fast Track** to jump the TeleOp queue. Limit: **6 Fast Track uses per UTC day, shared across all robots**. After 6 uses, the user joins normally without priority.

### Queue Mutual Exclusion (All Tiers)

A user can only be in **one robot queue** at a time. Attempting to join a second queue while already waiting or active on another robot is rejected.

### Error Messages Reference

| Scenario | HTTP Status | Message prefix |
|----------|------------|----------------|
| Explorer tries to join any queue | 403 | `"Explorer tier cannot use robots"` |
| Amplifier exceeds daily `training` limit | 403 | `"Amplifier members can join the queue for {robot_name} up to 3 times per day (UTC)"` |
| Amplifier exceeds lifetime `open` limit | 403 | `"Amplifier members have reached the 3 total uses limit for {robot_name}"` — frontend shows upgrade modal |
| Innovator exceeds daily Fast Track limit | 200 (queued normally) | `"You have reached the maximum 6 fast tracks a day. Please come back tomorrow."` |
| User already in another queue | 403 | (indicates already in queue) |

---

## 11. Robot Reservation

**Innovator Members only.** Allows booking a physical in-person demo or dedicated remote TeleOp session.

- User submits: email, first name, last name, phone number, project/company, location, Telegram handle, and robot name.
- A confirmation email is sent to the user automatically.
- Reservation records are stored for follow-up by the operations team.

---

## 12. Operator System

The Operator program enables users who own physical robots to contribute training data to the VLA Foundry.

### Lifecycle

```
Register Robot(s) → Submit Application → Admin Review → Approved (operator role)
                                                      ↓
                                             Upload Data → QA Review → Dashboard
```

### Robot Registration

- Users select a **manufacturer and model** from the platform-approved catalog.
- A **serial number** is required and validated against manufacturer-specific format rules.
- Each user can register multiple robots.
- One robot is designated as the **default data producer** at all times.
- Robots with existing upload history **cannot be deleted**.
- If all robots are removed, the user's `operator` role is automatically revoked.

### Operator Membership Application

- The user must have at least one registered robot before applying.
- The applicant must confirm with a verified email address associated with their account.
- Only one `pending` application is allowed at a time.
- An email notification is sent to system administrators upon submission.
- Application statuses: `pending` → `approved` or `denied`.
- On approval, the user receives a confirmation email and gains the `operator` role.

---

## 13. Referral Program — End-to-End Flow

Every registered user has a unique, permanent **referral code**. Sharing this code with new users earns the referrer two types of ongoing rewards.

### Roles

| Role | Description |
|------|-------------|
| **Referrer** | The existing user who shares their referral code |
| **Referee** | The new user who registers using the referrer's code |

---

### Entry Point

The referral program is accessible at **[https://app.prismax.ai/invite](https://app.prismax.ai/invite)**. Users can view their referral code, share it, and check their reward status from this page.

---

### Step 1 — Referrer Shares Their Code

The referrer visits [https://app.prismax.ai/invite](https://app.prismax.ai/invite) to find their unique referral code and shares it (e.g., via a link, social post, or direct message). Each user has exactly one code and it never changes.

---

### Step 2 — Referee Registers with the Code

When a new user signs up, they can enter a referral code during registration. The code is recorded at account creation time and **cannot be changed afterwards**. A referral relationship is only established if the code is entered at the moment of first sign-up.

---

### Step 3 — Referee Earns Points Normally

After registering, the referee uses the platform as usual — logging in daily, completing quizzes, doing TeleOp sessions, etc. Every point the referee accumulates contributes to the referrer's future revenue-share reward.

---

### Step 4 — Referrer Claims Rewards

The referrer visits their referral dashboard and triggers a reward settlement. The system calculates and issues any outstanding rewards at that moment. There is no automatic push — the referrer must check their dashboard to collect.

Two reward types are settled together:

#### A. Invite Bonus (per referred user)

- **Amount:** 500 points for each user the referrer has brought in.
- **Logic:** The system tracks the total invite bonus already paid out. Each time the referrer checks, it pays only the incremental difference — so if two new referees have joined since the last check, 1,000 points are issued.
- **Cap:** No cap; scales with the number of referees.

#### B. Revenue Share (ongoing, 10%)

- **Amount:** 10% of the cumulative total points earned by **all** of the referrer's referees, across their entire lifetime on the platform.
- **Logic:** The system computes `floor(total_referee_points × 10%)`, subtracts what has already been paid out, and issues only the new increment.
- **Example:** If the referrer's three referees have earned 4,000 points in total since last settlement, the referrer receives 400 new points.

---

### Reward Summary Table

| Reward Type | Trigger | Amount | Anti-Duplication |
|-------------|---------|--------|-----------------|
| Invite bonus | New referee joins via code | 500 pts per referee | Incremental — only unpaid referees are counted |
| Revenue share | Referrer checks dashboard | 10% of all referees' cumulative points | Incremental — only the increase since last settlement is paid |

---

### Important Rules & Edge Cases

- **One-time binding:** A referee's referral code is locked at registration. Re-login or re-linking a wallet does not overwrite it.
- **No self-referral:** The system stores the code entered by the new user — referrers cannot enter their own code.
- **Rewards do not expire:** Unclaimed referral rewards accumulate indefinitely and are paid in full whenever the referrer next visits their dashboard.
- **Referee points count in full:** Points earned by a referee from any source (login, quiz, TeleOp, etc.) all contribute to the referrer's 10% share.
- **No cap on referees:** A referrer can invite an unlimited number of users.
