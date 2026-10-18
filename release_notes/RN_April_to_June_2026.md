# Release Note — April to June 2026

## New Features & Improvements

### Robotics Data

#### Data Browsing

- A sample details page is now available in the Robotics Data section for deeper episode-level inspection.
- Filters have been added to the Robotics Data tab to make browsing large datasets easier.

#### Data Download

- Curated data packages can now be downloaded directly from the website.
- A manifest.json file can be exported for selected episodes, providing a structured index of all included data files and metadata.
- An API package can be created for selected episodes; the resulting Package ID can be used to download data programmatically via API key.

#### AI Assistant — HEX

- HEX, an AI Data Assistant, is now live. It helps users navigate the platform and understand their data by answering questions related to platform content and collections.

---

### VLA

#### Upload Data

- Users can apply to become an operator and upload robotics data (MCAP + videos) mapped to various task scenarios.
- An operators dashboard is now available, giving operators a centralised view to manage and track their submissions.
- Resumable uploads are now supported — if an upload is interrupted, it can be continued from where it left off without starting over.
- An upload history page has been added for operators to review past submissions at a glance.
- Scenario categories can now be selected during the upload flow to better organise and tag collected data.

#### Verify Quality

- Verify Quality is now open to eligible members. Amplifier members can apply to become a Quality Assurance reviewer with 10 review chances per cycle; Innovator members receive 30.
- A review history page is available for validators to track their past activity and submissions.
- Three informational pages have been introduced to help users understand the programme: How Selection Works, View Scoring Rules, and My Earnings.
- After completing a review, a confirmation popup displays the points earned for that submission.
- A warning is shown if a validator tries to leave before completing all episodes in a batch; any unsubmitted answers are preserved in case the page is accidentally closed or refreshed.

#### Register Robot

- Robots from supported manufacturers — Airbot, AGILEX, I2RT Robotics, and Realman — can now be registered on the platform and used for data collection tasks.

---

### Robot Fleet

- The Robot Fleet section has been redesigned as a hardware marketplace. Users can browse PrismaX-validated robots, view full specifications, and purchase directly from the platform.
- Currently listed models include Piper (Agilex Robotics), TOK2 (Airbot), and YAM (I2RT Robotics) — all validated to meet PrismaX data quality standards.

---

### Platform & Account

- Chain selection has been moved into the Connect Modal for a cleaner and more intuitive wallet connection flow.

---

## Bug Fixes

- Fixed an issue where robot reward points would occasionally fail to be applied to a user's account.
- Fixed network errors encountered during tele-operation sessions.
- Resolved a security vulnerability based on user-reported feedback.
- Invalid or expired session tokens are now detected automatically and handled gracefully to prevent unexpected errors.
