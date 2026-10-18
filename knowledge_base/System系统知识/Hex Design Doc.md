## **Hex Design Doc**

[Chloe Wang](mailto:chloewang200@gmail.com)

## **1\. Summary**

**Problem**: The dataset is large (\~50k+ episodes) so users cannot browse everything. They need to 

(1) see a small, representative sample,

 (2) express intent (“more lighting variation”, “90+ quality”, “failed attempts”, “different arms”), 

(3) get a bounded set of recommended episodes, and 

(4) download MP4/MCAP.

**Goals**

* Hex is a conversational assistant grounded in PrismaX metadata \+ optional embeddings, not free-form invention of URLs.  
* Recommendations are explainable (filters \+ similarity scores \+ why this episode).  
* Same task\_id / scenario often groups “same task type”; variation is across uploads, machines, conditions, and episode-level attributes.  
* Reuse existing download pipeline (/data/downloads/\*, manifests, signed URLs) where possible.

Hex should not be implemented as a free-form chatbot bolted onto the right rail. The core product is a guided dataset selection workflow with a chat surface attached to it.

The correct model is:

* users select sample episodes from a curated preview grid  
* Hex converts that selection into a live retrieval state  
* the UI shows a persistent selection summary and recommendation summary  
* Hex returns structured recommendation payloads plus short natural-language explanations  
* downloads remain deterministic and grounded in validated episode IDs and signed URLs

### **Data model signals already available**

The repo and current notes indicate usable source entities:

* data\_tasks for task / scenario  
* data\_machines for robot type  
* data\_uploads for batch ownership and lifecycle  
* data\_episodes for atomic downloadable items  
* data\_qa\_sessions for quality signals  
* data\_downloads for history

## **2\. Core concepts**

| Concept | Meaning in data |
| :---- | :---- |
| Scenario / task | data\_tasks.scenario (and related task metadata). Same scenario \= same high-level skill (e.g. Dish Wash). |
| Upload | data\_uploads — one operator batch for a task\_id \+ machine\_id. Status lifecycle (e.g. UPLOADING → … → DERIVED\_READY). |
| Episode | data\_episodes — one logical recording under an upload\_id; has raw\_mcap\_path, raw\_video\_folder\_path, status, links to GCS. |
| Machine type | data\_machines — product\_name, hardware class (Tok2, RealMan, YAM, …), tied via machine\_id on uploads/episodes. |
| Variation | Not a single column today. Operational definition: same task\_id (or scenario) with different (machine\_id, upload\_id, time, environment, operator, lighting proxy, …) plus embedding distance from user-selected “seed” episodes. |
| Quality | From QA: data\_qa\_sessions (qa\_score, review\_result, rounds). May be aggregated to upload- or episode-level for filtering. |
| Download package | Existing data\_downloads \+ POST /data/downloads/ui / manifest — operator-scoped, selected\_upload\_ids, expands to episode assets (MCAP \+ MP4 slots). |

Important constraint: Today /data/downloadable-uploads lists uploads but does not filter by user; /data/downloads/\* requires operator \+ matching user\_id. Product must decide: Hex-assisted download for operators only, internal researchers, or new role \+ row-level security (see §7).

## **3\. User Flow**

### **3.1 Discovery (Preview / Dataset hub)**

1. Open Preview Datasets (or dedicated Hex panel).  
2. See faceted sample grid (scenario, machine, quality band, duration) — server returns small page (e.g. 20–50 cards), not full corpus.  
3. Hover → check to pin seed episodes (episode\_id \+ upload\_id \+ task context).  
4. Optional: filters (scenario, machine, min QA score, date, “has MP4 only”, etc.).

### **3.2 Conversation (Hex)**

5. User opens Hex; system sends session id \+ seed episode ids \+ current filters to backend.  
6. User messages: refinements (“more lighting”, “90+ only”, “include failures”, “different arms”).  
7. Hex returns structured reply: human text \+ recommended\_episode\_ids (or upload-level bundles) \+ explanations \+ estimated size / hours.

### **3.3 Selection and download**

8. User accepts subset of recommendations (checkboxes).  
9. Browser download: call POST /data/downloads/ui (existing) with resolved upload\_id list (and policy for which episodes inside upload — today download is upload-scoped raw episodes; may need episode-level filter extension — see §6).  
10. API / JSON: POST /data/downloads/manifest \+ GET /data/downloads/script for scripted pull.  
11. History: read GET /data/downloads/history; optionally new hex\_sessions history for audit.

### **3.4 Feedback**

12. Thumbs / “bad match” → logged for tuning retrieval weights (future).

## **4\. Data access — existing tables (read paths)**

Primary DB: Cloud SQL Postgres (data pipeline service already uses it).

### **4.1 data\_tasks**

* Use: Scenario name, task\_id, data\_format, any future tags (environment type, difficulty).  
* Columns (from code): task\_id, scenario, data\_format, …

### **4.2 data\_machines**

* Use: Machine type / vendor string (product\_name, etc.), machine\_id, user\_id (producer).  
* Join: data\_uploads.machine\_id, data\_episodes.machine\_id.

### **4.3 data\_uploads**

* Use: Batch boundary, status, user\_id, task\_id, machine\_id, created\_at, validation payloads if present.  
* Hex: Filter “eligible for download” (e.g. status in allowed set), time range, producer.

### **4.4 data\_episodes**

* Use: Atomic unit for “video \+ mcap”; episode\_id, upload\_id, task\_id, machine\_id, status (DERIVED\_READY for preview MP4s), paths to raw/derived.  
* Hex: Primary key for recommendations; join to QA aggregates.

### **4.5 data\_qa\_sessions**

* Use: Quality signals per upload/round; qa\_score, review\_result JSONB, upload\_id, qa\_round, user\_id, timestamps.  
* Hex: “Score 90+” filters — define episode-level vs upload-level score (may require SQL view or denormalized column).

### **4.6 data\_downloads**

* Use: Past download jobs for “History” tab; selected\_upload\_ids, episode\_count, total\_bytes, created\_at, status.

### **4.7 users (via existing token resolution)**

* Use: Role (operator, QA roles) for authorization; Hex must not bypass existing \_get\_user\_by\_token / role checks.

## **5\. Data access — proposed extensions**

| Artifact | Purpose |
| :---- | :---- |
| episode\_metadata view or table | Denormalized: episode\_id, upload\_id, task\_id, scenario, machine\_id, product\_name, status, duration\_seconds (if derivable), has\_mp4, qa\_score\_effective, created\_at. Speeds listing \+ filters. |
| episode\_embedding (episode\_id, model\_version, vector)\` | Optional store in pgvector or external Vertex / Pinecone. Enables “similar to seeds.” |
| hex\_sessions table | session\_id, user\_id, created\_at, seed\_episode\_ids\[\], last\_filters jsonb, model\_version. |
| hex\_messages table | session\_id, role, content, tool\_calls jsonb, created\_at. Audit \+ replay. |
| hex\_recommendation\_sets table | session\_id, message\_id, episode\_ids\[\], scores jsonb, rationale text, expires\_at. |
| Indexes | (task\_id, status), (machine\_id, status), (upload\_id), GIN on metadata jsonb if used, IVFFlat/HNSW on vectors if pgvector. |

Variation modeling (v1 heuristic):  
variation\_key \= hash(task\_id, machine\_id, upload\_id) or clustering on embeddings within task\_id. Document as product rule, refine with ML later.

## **6\. APIs that we can reuse**

| Method | Route | Role | Purpose for Hex |
| :---- | :---- | :---- | :---- |
| GET | /data/tasks | Public in code | Scenario list / facets. |
| GET | /data/machines | Public in code | Machine catalog (careful: may expose all machines — tighten if needed). |
| GET | /data/downloadable-uploads | Operator | Candidate uploads list (today not user-scoped — fix before production??). |
| POST | /data/downloads/ui | Operator | Signed URL bundle for UI download. |
| POST | /data/downloads/manifest | Operator | Manifest JSON for API/script. |
| GET | /data/downloads/script | Operator | download.py. |
| GET | /data/downloads/history | Operator | History tab. |
| GET | /data/public/task-samples | Query upload\_ids | Preview MCAP \+ Env/Left/Right URLs for DERIVED\_READY episodes. |
| GET | /data/qa/uploads/... | QA | Different flow; not primary for Hex consumer download unless product merges. |

Gap for “episode-level download selection”:  
\_prepare\_download\_payload pulls all episodes under selected upload\_ids. If Hex recommends episodes 5,6,9 across uploads, product needs either:

* A) POST /data/downloads/ui accepts selected\_episode\_ids (and server filters rows in \_fetch\_download\_episode\_rows), or  
* B) restrict Hex v0 to full-upload download only (poor UX for your mock).

Recommend A as a tracked API change.

## **7\. APIs — new (Hex-specific)**

| Method | Route | Auth | Body / query | Response |
| :---- | :---- | :---- | :---- | :---- |
| POST | /data/hex/sessions | Logged-in (role TBD) | { "seed\_episode\_ids": \[…\], "filters": {…} } | { session\_id, echo\_seeds\_summary } |
| POST | /data/hex/sessions/:id/messages | Same | { "text": "…" } | Streaming or JSON: { reply, recommended\_episode\_ids\[\], facets\_used, disclaimers } |
| GET | /data/hex/sessions/:id | Same | — | Session \+ last recommendations |
| POST | /data/hex/sessions/:id/accept | Same | { "episode\_ids": \[…\] } | Validates eligibility → returns download\_job\_id or payload compatible with existing download flow |
| GET | /data/episodes/sample | Same | Facets \+ pagination | Curated small sample for UI (server-side sampling, deterministic seed) |
| GET | /data/episodes/:id/summary | Same | — | Card fields: task, machine, duration proxy, QA score, flags MP4/MCAP |

Internal (not necessarily public HTTP):

* Retriever worker: batch embedding, index refresh, scheduled ETL from data\_episodes where status \= DERIVED\_READY.

LLM orchestration:

* Backend calls OpenAI / Vertex with tools: search\_episodes(filters), similar\_to(episode\_ids, k), explain\_eligibility(episode\_ids), create\_download\_package(episode\_ids) (tool wraps existing download logic).

## 

## **8\. Hex response model**

Hex produces two response UI types:

### **4.1 Response UI type A: persistent selection summary widget**

This is a sticky panel or sticky card at the top of the Hex rail.![][image1]

**Keep current selection over 2 seconds \- run**

Purpose:

* reflect the current selected seed episodes  
* update instantly when user selection changes  
* show live counts and loading states  
* anchor the conversation in shared state

Fields:

* selected episode count  
* grouped task summary  
* current applied criteria chips  
* current recommendation count  
* breakdown by task  
* CTA buttons

**Design rule:**

* this widget should always exist once at least one seed episode is selected?  
* It’s sticky on top of chat?  
* it should not append a new chat message on every selection change  
* User selection changes should recompute the summary in place

This should be driven by frontend state plus a cheap retrieval/stats call. It should feel instant. If backend recalculation takes time, show:

* immediate optimistic selection update  
* “Searching…” loading state for recommendation count  
* Also need to create a db for this

### **4.2 Response type B: conversational result cards**

![][image2]![][image3]

These are persisted chat messages.

They appear when the user:

* clicks a CTA  
* types a message  
* applies or removes criteria  
* accepts or rejects a recommendation batch

Each assistant message may include:

* text  
* intent  
* criteria\_delta  
* recommendation\_set\_id  
* recommendation\_summary  
* action\_buttons  
* optional structured facets or explanation chips

These messages are persisted in the Hex session and restored on refresh.

Find more variation \- 

Refine criteria \- add new variation criteria

Tell user what variation to add

When clicking refine criteria

- User select a variation and add to this 

**If user can’t find a satisfied video \- and want to be able to submit a request \-\> tell us what you want and we will record and like an inquiry form, what data you need , when do you need, ask their contact info**

- 

### **4.3 Response type C: Plain text responses**

* plain text-only assistant messages are valid and should be supported  
* not every assistant turn needs a “generative UI widget”  
* a result card can be:  
  * text only  
  * text plus actions  
  * text plus structured recommendation summary  
  * text plus a richer widget payload

Use plain text-only replies for cases like other then find more variations and refine criteria results?

## **9\. User Intent model**

### **5.1 Canonical intents**

### **9.1 intent taxonomy:**

Currently shown in the UI

* Selection\_changed  
  *  the user changed the currently selected seed episodes, so Hex should refresh the summary and recommendation preview.  
* Find\_more\_variations   
  * the user wants more examples similar to the seeds, usually with broader diversity across uploads, machines, or environments.  
* Refine\_criteria  
  * the user wants to narrow or reshape results by adding explicit constraints such as quality, lighting, or robot type.

—------------------

What we might also support?

* Apply\_quick\_filter  
  * the user clicked a preset option like “90+ only” or “different robot arms” that maps to a known filter bundle.  
* Free\_text\_refinement  
  * the user typed a natural-language request that must be interpreted and normalized into structured retrieval filters.  
* Add\_recommendations\_to\_selection  
  * the user wants accepted recommended episodes added into the active selection for later download.  
* Remove\_recommendations\_from\_selection  
  * the user wants previously accepted recommended episodes removed from the active selection  
* Download  
  * the user is ready to turn the current accepted selection into a validated download package or manifest. Download for them based on their desired format  
* Show\_history  
  * the user wants to see prior Hex sessions, recommendation sets, or download history.  
* Explain\_results  
  * the user wants Hex to explain why a set of episodes was recommended or how it differs from the seed set.  
* More?

### **9.2 “Find more variations” vs “Refine criteria”**

#### **Find more variations**

![][image4]

Meaning:

* broaden within the same task structure  
  * But by how much?  
* preserve seed intent  
* intentionally increase diversity

Default system behavior:

* same scenario / task family  
* relaxed similarity threshold  
* favor distinct machine IDs, uploads, environments, time buckets  
* **no extra user text required \- this is just a button click**  
  * **Or should Hex follow up asking by how much & what variations**  
    * **E.g. user say “more lighting variation”**

UI behavior:

* clicking it should be enough to run a query  
* assistant can optionally follow with refinement suggestions after showing results

#### **Refine criteria**

![][image5]

Meaning:

* narrow or reshape the result set using explicit filters

What’s the default system behavior?

* assistant should ask a constrained follow-up if criteria are missing  
* or expose structured chips / controls immediately

Examples:

* lighting  
* quality threshold  
* failed vs successful outcomes  
* robot arm family  
* duration band  
* date range

UI behavior:

* clicking it should either open a criteria composer or create an assistant message asking “What do you want to refine?”  
* this is a better place for “buttons / options” than Find more variations

## **10\. User Scenarios**

### **Scenario: user selection changes**

Example:

* user checks or unchecks sample cards in the grid

Under the hood:

1. Frontend updates local `seed_episode_ids` immediately.  
2. Frontend debounces `POST /data/hex/summary`.  
3. Backend reads:  
   * episode\_metadata  
   * optional cached stats for the same seed/filter combination  
4. Backend writes:  
   * latest `seed_episode_ids` to `hex_sessions`  
   * updated\_at  
5. Backend returns:  
   * selection count  
   * grouped task summary  
   * recommendation count preview  
   * loading or ready state

Stored state:

* DB stores the canonical selection state  
* cache stores computed summary / counts

### **Scenario: user says “find more variations”**

Example:

* user clicks `Find More Variations`  
* or types “find more variations based on my samples”

Under the hood:

1. Frontend sends `POST /data/hex/sessions/:id/messages` with the action or text.  
2. Backend resolves the request to `find_more_variations`.  
3. Backend reads:  
   * current `seed_episode_ids` from `hex_sessions`  
   * episode\_metadata  
   * optional `data_qa_sessions` rollups  
   * optional cached recommendation results  
4. Backend calls:  
   * get\_episode\_stats(filters)  
   * `search_episodes(...)` for a heuristic same-task candidate set  
   * later, `find_similar_episodes(...)` when embeddings exist  
5. Backend ranks for diversity:  
   * same task family  
   * different uploads  
   * different machines if allowed  
   * optional QA threshold  
6. Backend writes:  
   * a new `hex_messages` row  
   * a new `hex_recommendation_sets` row  
   * updates `hex_sessions.active_recommendation_set_id`  
7. Backend returns:  
   * assistant text  
   * recommendation summary widget payload  
   * action buttons

Stored state:

* DB stores the recommendation set and message  
* cache stores short-lived candidate/result summaries for fast repeat access

### **Scenario: user says “refine criteria”**

Example:

* user clicks `Refine Criteria`  
* user types “quality 90+ only”  
* user types “different robot arms”

Under the hood:

1. Frontend sends `POST /data/hex/sessions/:id/messages`.  
2. Backend resolves one of:  
   * refine\_criteria  
   * apply\_quick\_filter  
   * free\_text\_refinement  
3. Backend reads:  
   * current session criteria from `hex_sessions`  
   * current active recommendation set if one exists  
   * episode\_metadata  
4. Backend normalizes the request into structured criteria:  
   * min\_qa\_score=90  
   * machine\_family\!=seed\_machine\_family  
   * lighting in \[...\]  
5. Backend reruns:  
   * get\_episode\_stats(filters)  
   * search\_episodes(filters, ...)  
   * later, `find_similar_episodes(seed_episode_ids, filters, ...)`  
6. Backend writes:  
   * updated `active_criteria` on `hex_sessions`  
   * a new `hex_messages` row  
   * a new `hex_recommendation_sets` row  
7. Backend returns:  
   * text reply  
   * recommendation summary  
   * updated criteria chips

Stored state:

* DB stores normalized criteria, not just raw user text  
* cache stores filtered counts and repeated query results

### 

### **Scenario: user says “add to selection”**

Example:

* user clicks `Add to Selection`  
* user checks a subset of recommended episodes and confirms

Under the hood:

1. Frontend sends accepted episode IDs to `POST /data/hex/sessions/:id/accept`.  
2. Backend reads:  
   * the current recommendation set  
   * accepted episode IDs  
   * authorization / eligibility via episode search or download validation helpers  
3. Backend writes:  
   * accepted IDs into session state  
   * a new message recording the selection change  
4. Backend returns:  
   * updated selection counts  
   * estimated package size/count

Stored state:

* DB stores accepted recommendation IDs as part of session state  
* cache is optional here

### **Scenario: user says “download”**

Example:

* user clicks a download button  
* or types “download these”

Under the hood:

1. Frontend sends a download request using the currently accepted `selected_episode_ids`.  
2. Backend resolves the request to `prepare_download`.  
3. Backend reads:  
   * session selection state  
   * eligible episode rows  
   * storage metadata needed for signed URLs  
4. Backend validates:  
   * user permissions  
   * episode existence  
   * downloadable asset completeness  
   * optional package size thresholds  
5. Backend calls:  
   * `POST /data/downloads/ui` for browser flow  
   * or `POST /data/downloads/manifest` for API / script flow  
6. Backend writes:  
   * data\_downloads  
   * optional Hex session message noting the download was prepared  
7. Backend returns:  
   * files for browser download  
   * or manifest payload for script download

Stored state:

* `data_downloads` remains the canonical download audit table  
* Hex session may store only the fact that a download was triggered, not all signed URLs

Scenario: user asks “why these results?”

Example:

* “why is this a match?”  
* “why these and not the others?”

Under the hood:

1. Frontend sends `POST /data/hex/sessions/:id/messages`.  
2. Backend resolves `explain_results`.  
3. Backend reads:  
   * current seed episodes  
   * current recommendation set  
   * score metadata / retrieval rationale  
   * optional compare facts from `get_episode_summaries(...)` or `compare_episodes(...)`  
4. Backend optionally calls the LLM to produce a short explanation from the structured facts.  
5. Backend writes:  
   * plain text message to `hex_messages`  
6. Backend returns:  
   * usually text only  
   * optionally simple explanation chips

Stored state:

* DB stores the explanation message  
* cache is not required unless these explanations become expensive

## 

1. ### **Data related**

| User intent | Verdict | Current API / DB | Gap / notes | AI tool API |
| ----- | ----- | ----- | ----- | ----- |
| Find all episodes recorded with **this robot arm** (machine type, e.g. RealMan / Tok2) | **Partial** | data\_episodes.machine\_id \+ data\_machines.product\_name (join). GET /data/registered-machines is **user-scoped**; GET /data/machines returns **all** rows (no auth in code) — risky for product. | No first-class “arm family” unless encoded in product\_name. Cross-operator search needs **auth \+ RLS**. | GET /data/episodes/search?machine\_product=…\&limit=… (auth, indexed join). |
| Episodes from **this machine\_id** only | **Support** (internal) | Same join; SQL straightforward. | No public episode search route today. | …/episodes/search?machine\_id=… |
| Episodes for **this upload\_id** | **Support** | data\_episodes by upload\_id. QA list paths already touch uploads. | UI/search endpoint missing. | GET /data/uploads/:id/episodes (public shape TBD). |
| **Pick and place** (and similar) by **task / scenario name** | **Partial** | data\_tasks.scenario \+ task\_id on episodes/uploads. GET /data/tasks lists tasks. | Scenario string match only; typos/synonyms need fuzzy search or LLM normalizing to task\_id. | GET /data/episodes/search?task\_id=… or ?scenario\_ilike=… |
| **Laundry folding \+ pick and place** (multi-task) | **Partial** | SQL WHERE task\_id IN (…) or scenario IN. | No API; combine client-side or server. | GET /data/episodes/search?task\_ids=1,2 |
| Episodes with **this QA score** (e.g. 90+) | **Partial** | data\_qa\_sessions has qa\_score, upload\_id; episode-level score not always explicit. | May need **view** “effective\_qa\_score per upload or episode”. | GET /data/episodes/search?min\_qa\_score=90 backed by view. |
| Episodes with **status** X (e.g. DERIVED\_READY only) | **Support** | data\_episodes.status used throughout pipeline. | Exposed only indirectly today (QA episodes, public samples). | …/search?status=DERIVED\_READY |
| “**Similar to** these episodes / this clip” | **Deferred** | DB has paths \+ task/machine; **no embedding index** in repo. | Needs **vectors** \+ ANN or external search \+ sync job. | POST /data/similar (body: seed episode\_ids, k, filters). |
| “With **this tag**” (lighting, failure, skill tag) | **Deferred** / **TBD** | review\_result JSONB may hold structured tags **if** QA pipeline writes them; not a generic taxonomy in code reviewed. | Define tag schema; backfill; index JSONB or side table. | GET /data/episodes/search?tags=lighting:low |
| **Count** how many videos / episodes (global) | **Partial** | COUNT(\*) on data\_episodes with filters. | No aggregate endpoint; heavy if unbounded. | GET /data/stats/episodes?filters… (cached/materialized for large N). |
| How many in **pick and place** only | **Partial** | COUNT join data\_tasks on scenario/task\_id. | Same as above. | Same stats API with task\_id. |
| **Total duration** of selected set / task / corpus | **TBD** | Blob sizes exist for downloads (total\_bytes); **wall-clock duration** per episode may be absent unless derived from MCAP/manifest offline. | Need **duration\_seconds** column or periodic ETL from manifests. | GET /data/stats/duration?… after column exists. |
| “**Any videos related to opening a book**” (semantic, no task name) | **Deferred** | Only if **scenario text** or **tags** happen to match; else no semantic retrieval. | Embeddings \+ captioning or human labels. | POST /data/semantic-search (vector \+ optional LLM rerank). |
| “What **variations** exist in this upload / task?” | **Partial** | Same upload\_id → multiple episode\_ids; across uploads same task\_id \+ different machine\_id / time. | “Variation” not one column; explain heuristics (machine, episode count, QA). | GET /data/uploads/:id/variation-summary or LLM \+ structured GROUP BY tool. |

### **2\. Download & package**

| User intent | Verdict | Current API / DB | Gap / notes | AI tool API |
| ----- | ----- | ----- | ----- | ----- |
| Download **these episodes** | **Partial** | POST /data/downloads/ui \+ manifest; \_fetch\_download\_episode\_rows selects by **upload\_id list**, not arbitrary episode subset. | **Episode-level selection** not supported end-to-end. | Extend download payload with selected\_episode\_ids \+ server filter. |
| What can I download? (operator) | **Partial** | GET /data/downloadable-uploads (upload-level). | Not user-scoped in code; policy fix. | Scoped list \+ optional episode preview row. |
| Past downloads | **Support** | GET /data/downloads/history, data\_downloads table. | Operator-only. | Expose to Hex as read tool with same auth. |

### **3\. Compare, explain, quality**

| User intent | Verdict | Current API / DB | Gap / notes | AI tool API |
| ----- | ----- | ----- | ----- | ----- |
| Why is episode A vs B different? | **TBD** | Machine, task, paths, QA JSON differ. | Needs **narration** from LLM \+ **structured diff** tool. | GET /data/episodes/compare?id1=\&id2= returns JSON facts for LLM. |
| Show **QA notes** for an upload | **Partial** | data\_qa\_sessions rows per upload/round. | No simple public “notes feed” API for arbitrary upload. | GET /data/uploads/:id/qa-summary |

### **4\. Meta / “general knowledge”**

| User intent | Verdict | Current API / DB | Gap / notes | AI tool API |
| ----- | ----- | ----- | ----- | ----- |
| “What is an upload\_id?” (product help) | **Support** | No DB; static docs / LLM system prompt. | — | Doc tool only. |
| “How does PrismaX define a dataset?” | **Support** | Same. | — | — |

### **5\. Niche / edge**

| User intent | Verdict | Current API / DB | Gap / notes | AI tool API |
| ----- | ----- | ----- | ----- | ----- |
| Episodes in **date range** | **Partial** | data\_uploads.created\_at, episode implicit via upload. | Episode-level **start\_time** if multi-day upload unclear. | …/search?created\_after=\&created\_before= |
| Episodes by **operator user** | **Partial** | data\_uploads.user\_id. | Needs permission to query others’ data. | Authz \+ …/search?producer\_user\_id= |
| “**Failed attempts**” only | **TBD** | Unless status or QA JSON encodes failure. | Define enum / tag. | Filter once schema exists. |
| Join **tele-op** or **live session** metadata | **Deferred** | Lives in other services / tables not covered here. | Cross-service correlation IDs if any. | Integration spec TBD. |

## **中文翻译**

## **1. 概要**

**问题**：数据集很大（约 5 万多个 episode），用户无法完整浏览所有内容。他们需要查看小而有代表性的样本、表达搜索意图（例如“更多光照变化”“质量 90+”“失败尝试”“不同机械臂”）、获得有边界的推荐 episode 集合，并下载 MP4/MCAP。

**目标**

* Hex 是一个基于 PrismaX 元数据和可选 embedding 的对话式助手，不应自由编造 URL。
* 推荐结果必须可解释，包括过滤条件、相似度分数，以及为什么推荐该 episode。
* 相同的 task_id / scenario 往往代表同一类任务；变化来自不同 upload、机器、条件和 episode 级属性。
* 尽可能复用现有下载流程，包括 `/data/downloads/*`、manifest 和 signed URL。

Hex 不应该只是一个挂在右侧栏里的自由聊天机器人。核心产品应该是一个带聊天界面的引导式数据集选择工作流：用户从 curated preview grid 中选择样本，Hex 把选择转换成实时 retrieval state，UI 持续展示选择摘要和推荐摘要，Hex 返回结构化推荐 payload 和简短自然语言解释，下载则保持确定性，并且必须基于已验证的 episode ID 和 signed URL。

### **已有可用数据模型信号**

当前 repo 和笔记显示可使用这些源实体：`data_tasks`（任务 / 场景）、`data_machines`（机器人类型）、`data_uploads`（批次归属和生命周期）、`data_episodes`（可下载的原子数据项）、`data_qa_sessions`（质量信号）、`data_downloads`（下载历史）。

## **2. 核心概念**

| 概念 | 数据含义 |
| :---- | :---- |
| Scenario / task | `data_tasks.scenario` 及相关 task metadata。相同 scenario 表示同一类高层技能，例如 Dish Wash。 |
| Upload | `data_uploads`，某个 operator 针对 task_id + machine_id 上传的一批数据，具有状态生命周期，例如 UPLOADING 到 DERIVED_READY。 |
| Episode | `data_episodes`，某个 upload_id 下的一段逻辑记录，包含 raw_mcap_path、raw_video_folder_path、status 和 GCS 链接。 |
| Machine type | `data_machines`，包括 product_name、硬件类别（Tok2、RealMan、YAM 等），通过 uploads/episodes 上的 machine_id 关联。 |
| Variation | 当前不是单一列。v1 可定义为：相同 task_id（或 scenario）下，不同 machine_id、upload_id、时间、环境、operator、光照代理信号等，再结合与 seed episode 的 embedding 距离。 |
| Quality | 来自 QA：`data_qa_sessions`，包括 qa_score、review_result、rounds。可聚合到 upload 或 episode 级别用于过滤。 |
| Download package | 现有 `data_downloads` + `POST /data/downloads/ui` + manifest。按 operator 范围、selected_upload_ids 展开成 episode 资产（MCAP + MP4 slots）。 |

重要约束：当前 `/data/downloadable-uploads` 会列出 uploads，但不按用户过滤；`/data/downloads/*` 需要 operator 和匹配的 user_id。产品需要决定 Hex 辅助下载面向 operator、内部研究员，还是新增角色和行级安全策略。

## **3. 用户流程**

### **3.1 发现（Preview / Dataset hub）**

1. 打开 Preview Datasets 或专用 Hex 面板。
2. 查看带 facet 的样本网格，例如 scenario、machine、quality band、duration。服务端返回小分页，例如 20 到 50 张卡片，而不是完整语料。
3. Hover 后勾选并 pin seed episodes，记录 episode_id、upload_id 和 task context。
4. 可选过滤条件：scenario、machine、最低 QA score、日期、仅有 MP4 等。

### **3.2 对话（Hex）**

5. 用户打开 Hex；系统把 session id、seed episode ids 和当前 filters 发送到后端。
6. 用户发送细化诉求，例如“更多光照”“只要 90+”“包含失败”“不同机械臂”。
7. Hex 返回结构化回复：自然语言文本、recommended_episode_ids（或 upload 级 bundle）、解释、预计大小 / 小时数。

### **3.3 选择、下载和反馈**

8. 用户勾选接受部分推荐。
9. 浏览器下载调用现有 `POST /data/downloads/ui`，传入解析后的 upload_id 列表。若需要 episode 级过滤，需要扩展现有接口。
10. API / JSON 下载调用 `POST /data/downloads/manifest` 和 `GET /data/downloads/script`。
11. 历史记录读取 `GET /data/downloads/history`；未来可增加 `hex_sessions` 历史用于审计。
12. 点赞 / “bad match” 记录下来，用于未来调优 retrieval 权重。

## **4. 数据访问：现有表**

* `data_tasks`：用于 scenario name、task_id、data_format 和未来 tags。
* `data_machines`：用于机器类型 / vendor 字符串、machine_id、user_id；可通过 uploads/episodes 上的 machine_id 关联。
* `data_uploads`：用于批次边界、状态、user_id、task_id、machine_id、created_at 和 validation payload。
* `data_episodes`：推荐的主键来源；表示“video + mcap”的原子单元，并可关联 QA 聚合。
* `data_qa_sessions`：每个 upload / round 的质量信号；“90+ 分”过滤需要定义 upload 级还是 episode 级有效分数。
* `data_downloads`：History tab 中的过去下载任务，包括 selected_upload_ids、episode_count、total_bytes、created_at、status。
* `users`：通过现有 token resolution 获取角色和权限；Hex 不能绕过 `_get_user_by_token` 或角色检查。

## **5. 建议扩展**

| 产物 | 目的 |
| :---- | :---- |
| `episode_metadata` view/table | 反范式字段：episode_id、upload_id、task_id、scenario、machine_id、product_name、status、duration_seconds、has_mp4、qa_score_effective、created_at，加速列表和过滤。 |
| `episode_embedding` | 可选向量存储，可用 pgvector、Vertex 或 Pinecone，支持“similar to seeds”。 |
| `hex_sessions` | 保存 session_id、user_id、created_at、seed_episode_ids、last_filters、model_version。 |
| `hex_messages` | 保存 session_id、role、content、tool_calls、created_at，用于审计和 replay。 |
| `hex_recommendation_sets` | 保存推荐 episode_ids、scores、rationale、expires_at。 |
| Indexes | 建议 `(task_id, status)`、`(machine_id, status)`、`(upload_id)`、metadata JSONB GIN、向量 IVFFlat/HNSW。 |

v1 的 variation 建模可以先使用启发式：`variation_key = hash(task_id, machine_id, upload_id)`，或在 task_id 内基于 embedding 聚类。先作为产品规则文档化，之后再用 ML 优化。

## **6. 可复用 API**

| 方法 | 路由 | 角色 | Hex 用途 |
| :---- | :---- | :---- | :---- |
| GET | `/data/tasks` | 代码中为 public | 场景列表 / facets。 |
| GET | `/data/machines` | 代码中为 public | 机器目录；注意可能暴露所有机器，生产前需要收紧。 |
| GET | `/data/downloadable-uploads` | Operator | 候选 upload 列表；当前未按用户隔离，需要修复。 |
| POST | `/data/downloads/ui` | Operator | UI 下载的 signed URL bundle。 |
| POST | `/data/downloads/manifest` | Operator | API / script 使用的 manifest JSON。 |
| GET | `/data/downloads/script` | Operator | `download.py`。 |
| GET | `/data/downloads/history` | Operator | History tab。 |
| GET | `/data/public/task-samples` | Query upload_ids | 预览 DERIVED_READY episodes 的 MCAP 与 Env/Left/Right URL。 |
| GET | `/data/qa/uploads/...` | QA | QA 流程，不是 Hex 消费者下载的主路径，除非产品合并。 |

“episode 级下载选择”的缺口：当前 `_prepare_download_payload` 会拉取 selected upload_ids 下的所有 episode。如果 Hex 推荐跨 upload 的 episode 5、6、9，产品需要让 `POST /data/downloads/ui` 接受 `selected_episode_ids` 并在服务端过滤，或者把 Hex v0 限制为整批 upload 下载。建议将前者作为明确 API 变更项。

## **7. 新增 Hex API**

| 方法 | 路由 | Auth | Body / query | Response |
| :---- | :---- | :---- | :---- | :---- |
| POST | `/data/hex/sessions` | Logged-in（角色待定） | seed_episode_ids 和 filters | session_id 与 seed 摘要 |
| POST | `/data/hex/sessions/:id/messages` | 同上 | 用户文本 | reply、recommended_episode_ids、facets_used、disclaimers |
| GET | `/data/hex/sessions/:id` | 同上 | - | session 和最新推荐 |
| POST | `/data/hex/sessions/:id/accept` | 同上 | episode_ids | 校验资格后返回 download_job_id 或兼容现有下载流的 payload |
| GET | `/data/episodes/sample` | 同上 | facets + pagination | 用于 UI 的 curated small sample |
| GET | `/data/episodes/:id/summary` | 同上 | - | 卡片字段：task、machine、duration proxy、QA score、MP4/MCAP flags |

内部 retriever worker 负责批量 embedding、刷新索引，并从 `data_episodes` 中按 `DERIVED_READY` 状态做计划 ETL。LLM 编排应通过工具完成：`search_episodes(filters)`、`similar_to(episode_ids, k)`、`explain_eligibility(episode_ids)`、`create_download_package(episode_ids)`。

## **8. Hex 响应模型**

### **8.1 响应类型 A：持久选择摘要组件**

这是 Hex rail 顶部的 sticky panel / sticky card，用于反映当前 seed episodes、在选择变化时即时更新、展示实时数量和 loading 状态，并将对话锚定在共享状态上。字段包括 selected episode count、grouped task summary、当前 criteria chips、推荐数量、按 task 的 breakdown 和 CTA buttons。

设计规则：一旦至少选择一个 seed episode，该组件应始终存在；可以 sticky 在 chat 顶部；每次选择变化不应追加新的聊天消息；用户选择变化时，应在原地重新计算摘要。如果后端较慢，先乐观更新选择，再显示“Searching...”的推荐数量 loading 状态。

### **8.2 响应类型 B：对话结果卡片**

这些是持久化的 chat messages。触发时机包括用户点击 CTA、输入消息、添加或移除条件、接受或拒绝一批推荐。每条 assistant message 可包含 text、intent、criteria_delta、recommendation_set_id、recommendation_summary、action_buttons，以及可选 structured facets 或 explanation chips。刷新页面时应从 Hex session 中恢复。

“Find more variation” 用于寻找更多变化；“Refine criteria” 用于增加新的 variation criteria。如果用户找不到满意视频，并希望提交需求，应提供一个需求收集流程：让用户说明想要什么数据、什么时候需要，并留下联系方式，类似 inquiry form。

### **8.3 响应类型 C：纯文本响应**

纯文本 assistant message 也应被支持。不是每一次 assistant turn 都需要 generative UI widget。结果可以是纯文本、文本加操作、文本加结构化推荐摘要，或文本加更丰富的 widget payload。

## **9. 用户意图模型**

当前 UI 中的 canonical intents：

* `Selection_changed`：用户改变了当前 seed episodes，Hex 应刷新摘要和推荐预览。
* `Find_more_variations`：用户希望基于 seeds 找更多类似样本，通常要求在 upload、machine 或 environment 上更有多样性。
* `Refine_criteria`：用户希望通过质量、光照、机器人类型等显式约束来收窄或调整结果。

可能支持的更多意图包括 `Apply_quick_filter`、`Free_text_refinement`、`Add_recommendations_to_selection`、`Remove_recommendations_from_selection`、`Download`、`Show_history`、`Explain_results`。

**Find more variations** 的含义是：在相同任务结构内扩展、保留 seed intent，并主动增加多样性。默认行为应保持同 scenario / task family，放宽相似度阈值，优先不同 machine IDs、uploads、environments 和 time buckets，并在有条件时考虑 QA 阈值。点击按钮应足以执行查询，assistant 可以在展示结果后再给出 refinement suggestions。

**Refine criteria** 的含义是：用明确过滤条件收窄或重塑结果。如果条件缺失，assistant 应提出受限追问，或者直接展示 structured chips / controls。可支持 lighting、quality threshold、failed vs successful outcomes、robot arm family、duration band、date range 等。

## **10. 用户场景**

### **10.1 用户选择变化**

前端立即更新本地 `seed_episode_ids`，debounce 调用 `POST /data/hex/summary`。后端读取 `episode_metadata` 和可选缓存统计，写入最新 `seed_episode_ids` 和 `updated_at` 到 `hex_sessions`，并返回选择数量、按任务分组摘要、推荐数量预览，以及 loading/ready 状态。

### **10.2 用户请求 “find more variations”**

前端向 `POST /data/hex/sessions/:id/messages` 发送 action 或文本。后端解析为 `find_more_variations`，读取当前 seed、`episode_metadata`、可选 QA rollups 和缓存推荐，调用 stats 和启发式 `search_episodes(...)`，未来可调用 embedding 版 `find_similar_episodes(...)`。后端按相同 task family、不同 uploads、不同 machines、可选 QA threshold 做 diversity ranking，写入新的 `hex_messages`、`hex_recommendation_sets`，并返回 assistant 文本、推荐摘要 widget payload 和 action buttons。

### **10.3 用户请求 “refine criteria”**

后端解析为 `refine_criteria`、`apply_quick_filter` 或 `free_text_refinement`，读取当前 session criteria、当前推荐集和 `episode_metadata`，归一化为结构化条件，例如 `min_qa_score=90`、`machine_family!=seed_machine_family`、`lighting in [...]`。随后重新运行 stats、search 和未来的相似搜索，写入 `active_criteria`、新 message 和新 recommendation set，并返回文本、推荐摘要和更新后的 criteria chips。

### **10.4 用户点击 “add to selection”**

前端把接受的 episode IDs 发送到 `POST /data/hex/sessions/:id/accept`。后端读取当前推荐集、接受的 episode IDs，并通过搜索或下载校验 helper 做授权和资格校验，然后把 accepted IDs 写入 session state，并返回更新后的选择数量和预计 package size/count。

### **10.5 用户请求 “download”**

前端使用当前 accepted `selected_episode_ids` 发送下载请求。后端解析为 `prepare_download`，读取 session selection state、可下载 episode rows 和生成 signed URL 所需的 storage metadata，校验用户权限、episode 是否存在、资产是否完整，以及可选 package size 阈值。后端调用 `POST /data/downloads/ui` 或 `POST /data/downloads/manifest`，写入 `data_downloads`，并返回浏览器下载文件或脚本下载所需 manifest。

### **10.6 用户询问 “why these results?”**

后端解析为 `explain_results`，读取当前 seed episodes、当前推荐集、分数元数据 / retrieval rationale，以及可选 compare facts。后端可调用 LLM，基于结构化事实生成简短解释，写入纯文本 message，并通常返回纯文本或简单 explanation chips。

## **11. 能力与缺口**

### **11.1 数据相关**

| 用户意图 | 结论 | 当前 API / DB | 缺口 / 备注 | AI 工具 API |
| ----- | ----- | ----- | ----- | ----- |
| 找到使用某种机械臂录制的所有 episodes | Partial | `data_episodes.machine_id` + `data_machines.product_name` join | 缺少一等公民 “arm family”；跨 operator 搜索需要 auth + RLS | `GET /data/episodes/search?machine_product=...` |
| 只找某个 machine_id 的 episodes | Support（内部） | 相同 join，SQL 直接 | 缺少公开 episode search route | `/episodes/search?machine_id=...` |
| 找某个 upload_id 的 episodes | Support | 按 upload_id 查询 `data_episodes` | 缺 UI/search endpoint | `GET /data/uploads/:id/episodes` |
| 按 task / scenario 找 Pick and place 等任务 | Partial | `data_tasks.scenario` + episodes/uploads 上的 task_id | 只有字符串匹配；错别字和同义词需要 fuzzy search 或 LLM 归一化 | `GET /data/episodes/search?task_id=...` |
| 多任务组合，例如 Laundry folding + pick and place | Partial | `WHERE task_id IN (...)` | 缺 API | `GET /data/episodes/search?task_ids=1,2` |
| QA score 过滤，例如 90+ | Partial | `data_qa_sessions.qa_score`、upload_id | 需要有效 QA score view | `GET /data/episodes/search?min_qa_score=90` |
| status 过滤，例如 DERIVED_READY | Support | `data_episodes.status` | 目前只间接暴露 | `/search?status=DERIVED_READY` |
| 与这些 episode / clip 相似 | Deferred | 有路径和 task/machine，但无 embedding index | 需要向量和 ANN 或外部搜索 | `POST /data/similar` |
| 按 tag，如 lighting、failure、skill tag | Deferred / TBD | QA JSONB 可能有结构化 tag | 需定义 tag schema、回填并建索引 | `/search?tags=lighting:low` |
| 统计全局视频 / episode 数量 | Partial | 带过滤的 COUNT | 缺 aggregate endpoint；无界查询会重 | `GET /data/stats/episodes` |
| 统计 Pick and place 数量 | Partial | join tasks 后 COUNT | 同上 | 同 stats API |
| 统计时长 | TBD | 下载里有 total_bytes，但 wall-clock duration 可能缺失 | 需要 `duration_seconds` 或离线 ETL | `GET /data/stats/duration` |
| 语义搜索“打开一本书相关视频” | Deferred | 仅 scenario 文本或 tags 命中时可用 | 需要 embedding、caption 或人工标签 | `POST /data/semantic-search` |
| 某 upload / task 有哪些 variation | Partial | 同 task_id 下不同 machine/time/upload 等 | Variation 不是单列，需解释启发式 | `/variation-summary` 或 LLM + GROUP BY tool |

### **11.2 下载和 package**

| 用户意图 | 结论 | 当前 API / DB | 缺口 / 备注 | AI 工具 API |
| ----- | ----- | ----- | ----- | ----- |
| 下载这些 episodes | Partial | `/data/downloads/ui` + manifest；当前按 upload_id 拉取 | 不支持任意 episode subset | 扩展 payload 支持 selected_episode_ids |
| 查询可下载内容 | Partial | `/data/downloadable-uploads` | 代码中未按用户隔离，需要 policy fix | scoped list + episode preview row |
| 过去下载 | Support | `/data/downloads/history` 和 `data_downloads` | Operator-only | 以同 auth 暴露给 Hex |

### **11.3 对比、解释、质量和边缘场景**

| 用户意图 | 结论 | 当前 API / DB | 缺口 / 备注 | AI 工具 API |
| ----- | ----- | ----- | ----- | ----- |
| 解释 episode A 和 B 的差异 | TBD | machine、task、paths、QA JSON 可比较 | 需要 LLM narration + structured diff tool | `GET /data/episodes/compare?id1=&id2=` |
| 展示某 upload 的 QA notes | Partial | 每个 upload/round 有 QA session rows | 缺简单 public notes feed API | `GET /data/uploads/:id/qa-summary` |
| “upload_id 是什么？” | Support | 不需要 DB | 静态文档或 LLM system prompt | Doc tool |
| “PrismaX 如何定义 dataset？” | Support | 不需要 DB | 静态文档或 LLM system prompt | Doc tool |
| 日期范围内的 episodes | Partial | `data_uploads.created_at` | 多天 upload 的 episode start_time 不明确 | `/search?created_after=&created_before=` |
| 按 operator user 查询 episodes | Partial | `data_uploads.user_id` | 查询他人数据需要权限策略 | authz + `producer_user_id` |
| 只要失败尝试 | TBD | 除非 status 或 QA JSON 编码了 failure | 需要 enum / tag | schema ready 后过滤 |
| 关联 tele-op 或 live session metadata | Deferred | 在其他服务 / 表中 | 需要跨服务 correlation ID | Integration spec TBD |

![][image6]

[image1]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAATIAAAD0CAYAAAAYAKrYAABDA0lEQVR4Xu2d97cbx5Wg5w/Yc/bs2dkzZ2fH4zBajxWYHtMjH3N8zDnnIOYoZoqkqExlBlGkMpWjbUmWZJvKkmXL2WN7nIPssWZ2PH9EL74L3tbFbTSI9x7IBxD3h+8AqK6uqq6u+rqqAVT/zT989jNJEARBI/M3PiAIgqDRCJEFQdDwhMiCIGh4QmRBEDQ8IbIgCBqeEFkQBA1PiCwIgoYnRBYEQcNTtcgua/lS0nvGoA5zVXu/TFp5XNWrR9I2bEgQBE3MwEGtSa8+vTN+qMR5RfbZL34+uXJ0S9JjwoDksr5f6jBfbOsh+5OOT9uCxDiAHr17Jl+64ktBEDQpOKBPvxZ59Z7Io6LIGIVdMapPRk6dQURYSM/nobQVTOwPKAiC5kYHN94XnooiY1rIiMpLydMyf1gy8uDsTLiFdCpNM9tCZEEQOJAYbvj8ZV/IOMNSUWTc4/JC8gKb9vi6ZMqja5Mhe6aJzAjz8RTS83kobSGyIAjKUM09s06LTAV25fTW5O+/9DkBmRGWNzoLkQVB0FEYlSEz7wxLh0WGpJZ++1CJwDwIjTheaCGyIAg6A37wzrB0WGSMxLy48iBuiCwIgq6CH7wzLCGyIAjqHvzgnWGpicj6rhqdjL1zcSY8RBYEQS3AD94ZlpqI7J+GXJX0Wz0mEx4iC4KgFuAH7wxLTUQ289nNycI39yaf6XVZiCwILgCXX3VF0j5pgnBFjysz2y918IN3hqUmIsvjgojsysuTN958syTsnqP3JO+++27Su2+fbPwyfPkrX06WLFuaCa8l/Qb2Tz741gfSAP22PNZtWJ9su2Z7JrwclP+dd9/JhG/asjn561//K/n444+T5SuXZ7ZfaD767neT3/3+d5nwrvLv//7vyWuvvZYJr5bWwa1SL0duvy2zrd6Zv2iBtO/33ntP2hTvCX/m2WeSu+6+KxP/zGNnMmHw0MMPV91H6g384J1h6bDI9OcX/MTCi0vhpxkX8ucXM+fMSjZu3iTvx7WPl5NLB/bx8rgYIhvQOrDDIjt1+lRy5vHHMuHlKCeynn16Jf/vP/8zuWbnjuTXv/518sknn2T2u9BcKJHtP3BtsnDJokx4tajIbrvj9sy2eufs2bPJ6Qful/eI6MUvvyjvn33u2eTue+7OxJ88dUomDGiPg9oGZcIbAfzgnWHpsMis0PQX/VZghPmRWK1FBlyVWvr3TV5+5ZXk+RdekLCjx4/JVQtRtRZO2LARw5O33n4r3WfLtq3y+tzzzyULFy9KVq+5Ojn7xhsyyrPbGeGRznvvv5/c/+ADJfkSh7xpFKQ9Z95cCX/7nbeT9z/4IPnqS1+V0ZgVGfmxDfHs2btH4k+dPi35xje/IWlt3b41uenmmyUOcKUlTqYMhXLynrCXX3k5I7L5C+dLZ+X9rj275f2iJYtL4pA/4YxwdHRC+f7jP/5DwteuXythyOgHP/yBiBEo01//+tfkF7/4RdJ3QL/k5ltvSf705z8lP/zRD2W/w9cflv2syKZMm5r86le/knjlRppsZ1+7/evf+Hry83/9efLxHz+WdLR+f/Ob3yRPPPmkdNLf/PY3UpbXXi+O0Pq3Dkg+/PDDtKz8eJLwe0+eTI+LY1GRPfbE43L8pPGtD7+V9G7pLXz00UcS56c/+6mIz5aViwTnhnP6la9+RaZ3nGekQviJk/dKPEZDjJKYNdAeucCyzzfPfjOZNWe2xDl+7wk5h4TTTiZMnijtkM+cc6Rt8+Y8P/jQQ2k7HTlmlLwiMupAR2pPPf2UhFOW8RPGS12evO+k5EX7tKO5RgM/eGdYOi0y0P9Y6i/6EdjF+ovSm2+9KY2DkzR4aJt0BBrUvAXz5OTSOceMGythus/efXtL0tDGqaOzF158MRUVDWHs+HHSAOx+NFAaKoJiqE7jGT5yRHL12jXSwZEoYVZkSIdGv2LVSslv1NjRUv6HH3kkuaUgBMLoOI+eeVSEgYQphy8DEuJ4p8+cLhL0Ihs6YlgqMo6f9/uu3V8S5w9/+EOydPkyERACmT5rhsSjLpetWCadmHgIgREd5UBGxDlw6GAqAyTBe6Szbfs2eT9i9MgSkZEXAqLMSIPy+bJwMbHb2Z+06IR/+eQvMkUmrk4tOW7iUs9ICnmffeOshCFXhMr50+P63ve/J23jl7/8ZVp2XpHMrj275DhpL9cePCDhN9x0o+R136n7SspK/XNhHDJ8qJwvBMvomfLQdjnXCxYvTMVGXTFzIJxR1IMPPyTlQrKEMV2kvRCPdkAbQY6Mpu3FF3bv3S1pIizS14sGIqMNMCvRvBA9Mp00dbJ8Jl0u2rRRPnMBtWk3CtSxd4alosiq/dN4NdT8T+OFqxMnZsbsmfIZAchVq/CeUQgn3ovs4HWHMukgMRoYHfb1r78u6bz62qvJkduOpDBisvtw74lpIPuxD43Rxmd0ZUVGg/fpsY2li7QMSNVOLSmH34eG+8BDD8r2VVevzogMkMmNN98k+9AxdRSgXNnzKukQxZHKX9MR2o9+9CMRM+IhHh2ckQfvCVdBEo5EVGSMhgjn/Z0FwavIkC1hjHLofIBAtRy6XbfpdvZXeXEcxEHm9h4ZtxU+/tOfZBvlR7jITNPm2BiJsJ2RFmGMYlRkpGXzfeTRR4plKshPhUcbsPXGOT567KiMsDjvSJ/XNevWyHbaIZIjvdvvvCPdR0b8pHGuvXI++N/g9oJcGRnqSA7x3HHXnSJGxM7FjHD6BaK197aYHtIG/dSSCx7lUpHZtg/k35RTS5bd6ew6ZB5ZDqiWy/g4kemVmKsmU02uRHr1YwqDNJiGZtK5ojh05ypIGsiO0RIiQkIvvfySXKU1LvHWbVgn72nUNBa+SdIrHaO15154vkRkMlUslJdGRF6UGZkgPK62NEC20/l0ekA5fBn0GKkrZOJFRlzkRPrcI1MhWBjlIB+kQ4elk/DaPrFdhKGjqWpFhlxIj/fkqyJjdIFQvv+D74sA2I/Rk5ZDt7Ov3a4jMo4fqSId4qvIPvz2hyIuyks8JIQsSYtREmVgtKnTbKb65MF5U5HxioCQPtNU9j924riEc7uCkeqPf/zjknrT2xc68lm+aoXUA6N4zh3tgJERIuMiQtyJUyZJXN4jZQRFW+Tca3vn3HLOuYjxWb8kshcg4nOPTL+t5MLHRfp8IiM/ewyky8jMhjUK1Jd3hqWiyIBFEbu6Jhn7k45P29LWRZFxkp9+5mlpUEz/mJYRzhSLeDSGPJFxVSQOjYh09J5W8V7UK+nICQ7fcL1sQyK8chUlXOO/+dZb0ohUZJSTm7Vsg9P3n5b46zduSO9d6BcXOlKj81EOXwagQxFebmoJlIcO+clfPknvL1mQBtuB+0qMjPQ+ksK9MxUW+1QSGbLkVaVnp5Y7du2U+Gynw/qysF3z1O3sT3mK+/01vV+EyBgl0VGL97f+S/KhY44eNyb57e9+m6aF5NiHC4qGcc+NV0Sm98sAsdOGmNprGqSvIy2F6SkXES5yjLKY+pIP55tzxH1V4iE2FRlwsZJ7nQX0Aoi4OIekt3L1Kplmsp3PhCND+yUR4tJ7sBqH8HIiY1SLyJCoFxm3D1SsjQZ+8M6wnFdkukJsZ2VW7QqxbR0VWQ4M230YaZcLrwRDecTmwwGhMFVhOqhhNDydDpSD0aEVYjXklYFRgw+zMLLyYZZpM6aV3MzmOBgpkB/3WOxx5aEiY6qa9y0ZUC9I3Ycr7Gu3qwhZ8YC0fXxA8sjLh3OPzY84OCZupvu4nA86u/9Wmbh5v9Ni6sgr59Gel0rn3e5n4f7YiFGflpVy8Lnc+VZoc5S5o+3oUoA+7J1hOa/IlAu9Zn9bjUQWXBxUZHmdvrNcqJ9vBI0NfvDOsFQtsgtNW4isoWBUqFO4WsI30HakEgSAH7wzLCGyIAjqHvzgnWEJkQVBUPfgB+8MS4gsCIK6Bz94Z1hCZEEQ1D34wTvDEiILgqDuwQ/eGZYQWRAEdQ9+8M6wNKTI+HMuv1C2lPvRIfBHbF0CRbFL4PBLbV3xoSt87dVXS8rDr7/5rx3bfP4WfqHvw7oKv97XvzpZbBlt+fh1ei3qoJZwDD7Ml58/WBNeackk/qDv/3NoefKpJ9O/HwHp6OoS/CuDX8dXWzf86p5f6fvwoOvgB+8MS0OKjH/zy5ImljLxgL9reJFYkfG+Fn+kpZPxfz3Kwq/G+ZsKHYhflvNfTB9fuVAi4+9aPlzL6MtXK5nXkjyRaR0jYcrP37v4Ua7+/cfjFw7w8F9Xu7QNItPFBezqFX6/cpAOF1kfHnQd/OCdYWlYkdnVCw4dPiQ/oqTR0cB1yRQauIpMl8Bh5Gb/p6idmP3Yn3LwB2P+I6dpsjIGfymp1CHoZPw5nP/osbIB5eL/c3Q68te0+H8hIwj+B/jK174mZeH/dpTNr9nFqIr/XZI3/820/7HzS7cwsuD/f/xdhrTyREYZffm0DsotVcOoh/T4EzP1wn/7dNkZuzSRz8seQ7nyc350UUxffvLy/xPU8rP8jn6mvJxHOyLjf7Z2iSVExjbKTTmod58ux0Va/BFc/9BPOP8pJT+2UV5bL37pHeITh/+MUi/6H0ufV9A56JfeGZaGFRkrQSiMqmhsTJHYzn/RaLysSKEio2PT+Ni+YdPGsiKjIxFGB2DxO/6wnC7DckXxj+G+LAqdjIbMH3OBfPVP2+RP+ewS3fz3k45Bh6Ws/FHdp8lIADGyUgV/mCYe4YhA43Ac/JGaV10YEpHniUzLaMundUC93XTLTSI78iJd6kKXuUEYwJ+T6cSEQ6UOyzGUKz8rfeSVX4/Bp+VFxjnTlUpUZJxjpMhaYxyPikz/SuXXpAOWTmJJHV2BguPhz/ScG0ZYpMM6d7ZeuOjwngsC0mI/6pbllXjPBUGPN+g6+ME7w9KwIvNheWs/qcjy1vKyImOERJiKjJEeK1doHucTme1kFvJHuHYaSedjqRnSZEUNyuuX36bjIL9bj9wqHbOcyHTpFjoRa/4ThiTyRFaujLYO/JpbjGB0xQ6kwJ+W2ebXWPNpKhxDufLrqg3lyg8qOosvP2kzavL3yOxacX5qWU5kSElWtTh3rrlnhtjYjzSpF+Rm64V4dg0xRpJ2ahkiqy34wTvDcsmITNd+opHp2k+MelRkupYXkrNreVUSma6ySX5clbVDkAcrm9r8fSezkD9TFtJiOkjnoKOQj8qNJazp1HaVDsqr003WI6skMoSjUx2OrTMiK7fmFivYkgeyQKqsOEv+fo016l+X8bZInV+RLb8XmS2/punT0ntk1B/yVPlbkenqqrpWXDUiIz/213h6m4FpPZ+pF9qRrRe/hhgXzTyR+bYSdBz84J1huWREBrruvV37iQZIg9O1vBCcv0fG9M2KjKmJ3FQuvKcjs4+mSxjTCY2r8LncDWrQBs92SedcGfjTtYoMgdGp7TMCmF7RGeggdHL2ZaTiRcYaVHzTxoiUOLyWE1leGbUOyq25xZI+rDVGuhw3opG83BprTEnLjVj1fqUvvxWZL78eg0+L8lMfwPRYz7Fd+43RLeeWNBgteZGVky1wW4Iy8l6XheaY+KzTSFsvfg0xJGpFxm0DFVneOnhB9eAH7wxLQ4qsEuW+grdUWu/JQ5kYmZEmItQbxYwguJns41cD6ejDMaqBuFpmXs+3FtX51sY6H3lrbpVbA82usUZdqQg8HS3/+eKcD79WXC3Qby5tvVSzhlhQG2hf3hmWS05ktYSGyhUYGI3ojVy+eazH8nYnTPHKrUgbBLWA/uadYQmRnQdkxsNM/GPVgiC4eOAH7wxLiCwIgroHP3hnWEJkQRDUPfjBO8MSIguCoO7BD94ZlhBZEAR1D37wzrCEyIIgqHvwg3eGJUQWBEHdgx+8MywhsiAI6h784J1hCZEFQVD34AfvDEuILAiCugc/eGdYLgmR9RjUJ2mZMCgZMHt40rpgVBAEdQT9kv5JP/V9t1rwg3eGpaFFdmW/nkm/qUOSATOGJS3tg5Jew/smV/XvFQRBHUG/pH8iNfor/db35fOBH7wzLA0rsh6DekvFUEG+4oIgqE9UaPRf36crgR+8MywNK7KQWBA0JiqzjozM8IN3hqVhRRYSC4LGhf7LNNP36zzwg3eGpSFFxo1DXzFBEDQWyMz37Tzwg3eGpSFFxrcgvlKCIGgs+BLA9+088IN3hqUhRcb82ldKEASNh+/beeAH7wxLiCwIgm7D9+088IN3hiVEFgRBt+H7dh74wTvDEiILgqDb8H07D/zgnWEJkQVB0G34vp0HfvDOsITIgiDoNnzfzgM/eGdYmlJkvUf3T2Y/t0WYdM/yzHboN6UtmfbQ2mTBN3YnSz88mCx+Z3/StmJ8Jl41TD21Os1v+JappdtbeycT71yazH91V7Lkg4PJkvcPJHO/vD0ZsdXFO8eoHdOTeV+9RuLOf3Vn0n5ksaTh4wVBI+D7dh74wTvD0pQiG3/zwmTptw8JC17fldmORJCXxrEgNx//fNj9J9y2pGTbgm/uzuShXDXQpFOQ1cwnNmbiwPyv7076jBmYyTcI6h3ft/PAD94ZlqYTGSMaKwEvspb21owoPGP2z86km8fgJWNK9vUi82lbRu2ckcYbvW92Zrtl+qPrM3kHQb3j+3Ye+ME7w9I0ImNKN/uFrRkBeJHNeHRdyXakhdzGXjfv030Koyiffjl6j+wvU0WbnhUZ/zXTcPLtObglaRnfmix8a6+ELX57f3FUVhiNMbXVuAu/uSfpOaQlM0LrO3FwpgxBUM/4vp0HfvDOsDSNyCYdXV7S6VMpOZFZYSAXu83uV819qTlf3pbJz4qM+3MSXpjGIjENH7x8XBq/bdnYpG1le0kagxaNlng9h/YtmQJzr82XYcCsYTKag94j+me2B0F34vt2HvjBO8PSNCKjk3upgBeZ3TZs4+TcbecT2fgbzX04vjA4996KTEdUjBRL9h/QMxXUqF0zk9F7Z6X7c5PfxuXGv26b8Vh2etl+66J0+4BZ8R/VoL7wfTsP/OCdYWkakVlmPrXpU8mUudnv6dnWksx6+tN9xt24IBNH6TW8X7L43WvTuIMLI6o8kWm8ciMpvsVkG/e+Zjy+Id1/3is7SuKlo7oCjCZ9OiGyC0u/oQOTHgMrX9SCfHzfzgM/eGdYQmTnERl5LXprXxp/7ss7ZMTk4ylznv/0Plz7kaK0zieycj8BoVxsY9Rm74UhOBvPTplJz6dTS5HdfeJoJqwch246nOw7tD/pP7Q1ue+B05nttULz8eHVMm3+zOT46Xsz4dVy/S03JicfPJUsvTp7/rrCjn27khtuvTETfini+3Ye+ME7wxIiyxPZwF7JhNuXpPGA0RFL9GbinoPfmdn4Yw/NKzC3ZIQ276VrJIz7XCq4ySdWZdJaeLZ4wx9RsT0t7zdKv2iYet/qzLHYMuTBfj7P8zFlzvRMWDnGThmfjJo4Nhkw7MKKTPPx4dXSVZFxbKMndT7/PBDZ9SGyEvCDd4YlRFZGZD2HtsjIy3Z8f2+qHMPWT8oII4/Jx1Yks5/dIu959WmRH9vGHpgjQswrh/0mlukvYT6vckw9XVlkO6/dk5x84JR01juO3SVSuvXOI7LtrhP3JNcVRkNsv/f++5J1W9dLvNvvuSPp2don2VXYd9vua1KRjZgwWkZzvGcEQ0clnXvuPZqcOH0ymbmw9Ocs85cvSk6cujc5ctdtMqobOGJQcuL+k8kthfzZn32Ip/m0tPWTsmn6bGPKd+NtN8tnyrj/umuTHgN6CZSb8Nvuvj0VGULiuI6ePJa0z5hYtg5sGY/dd1zCKdf46ROS46dOyOd7ThxLJswo3lu98/jd8n7QqCFpPvsPH0iuu/l6+ayS5/g4Vjm2QnqUI0RWCn7wzrCEyJzIuB9mp4LADfXeYwZk0vF0VGRTThZHWjIlND9+7Td1aBpv6NqJmXT7Tmorxm3tXfLzDh3ZzXpyU0rJtPjL29Nwfk/ny5/mX5AAnYwRGO/pkFdvWpdOLREJUuk7ZEBy7Q2HJO6QMcOlI06dOz2d8qnImCbRUUkLSalsEMz85QtFRJq3pjN36XyRE9M3REA6B2+8TvJcvnZFMqx9ZJrPolVLRTikP3LCGIFtiLJt9LBk3LQJktfaLeuSFetXi3hI8+7jR1PBHDt5XAS7bfd2kWi5OrB1RLpsR1SUhfrhOBAV9cN9M16pD43LfsiVcOQ+YcYkGVVef8sNIq+BIwdLehxLiKwU/OCdYQmROZHZm+cgo5yce2Kt80cms57dLCAcBNN+88IMJVPLghQJ40uAIVdPSMNH7ZmVLd+HB+XLgz6j+pf8zEK/nWS0ZsvKzzR8GTt7j4yOTSdnJDN70VwJsyKbvqBY3pUbrk7DGZXMWTwvIzI6OGLaXhg93XHs7rRTIxef78qCaOjIB248JPIjjooMoWi8NZvXpfkMnzBK5IcMrtm3s1iWQtmXmHtXuw/uK4rRCGLBisUST0VzqCBKZMl7Rmjl6sBCPPalDjSs16AWCR83tT1XZHsO7k3jz1gwW/JAxhqGDENkpeAH7wxLiKzCzy9SkIiDUdOwDZ+OlCp9k5l3s9/nx418+zs27o9pvMn3fnqfDPTLAPvZ5wudFVmfwf1EBDKFLEhi14G9JSKjg/KeTqyjlTyR3XDkJpHC5h1bC6OpVRVFxsiG9Dfv3CZs2L45FRll0ngbtm8qudlPHKa4t9xxRMpAGgsLotL4CI6pJCLRMOIhkWHjR0j6W3YV84TBo4Zm6sCXVUVGmTWMqauO1LSeEK0V2fa9n37zjMiIx8hUwxBdiKwU/OCdYQmRVSOyMvSfPqzmIvPYH7AytfX/EkgpiJURns8XOiMypmY6EuLz/usPigQ6KzLu++g3e+u3baooMm7eIw1GNNv37Ehuuv2WVGSM6IjDPSymZZrP6o1rZaSnP4NASOzHPTtGSHKPrTBdZNqI7EgP4TBC06klx7Rm81r5AoC4oyePy9SBL6uKbEwhLkIiDMEyokSCx+47ISJGopVERlmpX8pPWSlTiKwU/OCdYWlKkdWUgcWfUYzYPi27rQPwd6a2lePl2Oyv/MvBfTx+/c+002+rJUzlho4dJp3eb+soA4YPkhv3vCddBOPjWGyeKjLeI468fVtHtaXiUZBpS1vpPxq4z2anqZWotg7YzijOh1ebD3CPLO/YLlV8384DP3hnWEJkXYB7Vzq66zO22EmD2mNFFlxa+L6dB37wzrCEyLqAvVnvtwW1gymX/iQiuLTwfTsP/OCdYQmRdQHuOfH3on6TS6czQRBUh+/beeAH7wxLiCwIgm7D9+088IN3hiVEFgRBt+H7dh74wTvDEiILgqDb8H07D/zgnWEJkQVB0G34vp0HfvDOsITIgiDoNnzfzgM/eGdYQmRBEHQbvm/ngR+8MywhsiAIug3ft/PAD94ZlhBZEATdhu/beeAH7wxLiCwIgm7D9+088IN3hqVpRNZzWN9kwMzhxcerBbVn6VipX+rZ131J/S8ts29wUal0ni42vm/ngR+8MyxNITJO3IAZw5M+owcGFxjqmfqO+q9vyp2n7sD37Tzwg3eGpSlExijAn8jgwkF9R/3XP/48dQe+b+eBH7wzLM0hsmXRkS4m1HfUf/3jz1N34Pt2HvjBO8MSIgtqju8gUf/1iT9P3YHv23ngB+8MS4gsqDm+g0T91yf+PHUHvm/ngR+8MywhsnP0nzYsGTh3ZCY86Di+g1RT/8HFx5+n7sD37Tzwg3eGpelF1tI+SJ66PfOJDcLgczemZz2xKek7YXBJXBZR9PuP2Do1GbxsXEnY9IfWFp8f+USRvuNbM/vJvtunZ8JG7ZwhDyi5UN/yjSyT54Dpw5Jp96+Rsg6cPULCKMeMx4t1Mmb/HAmbeMfSwueN8sT1oasnZNJRfAepVP9QUl+F18nHVyT9pgwpW98KFx4f1lkGzhkpx6SfOV8zn9qcPgOUY+YRfhPvWi7n2+9fa+Qxg4W6sGG004l3LZOyzHikWNb+04YmU09fLXGnFs7fwJnFNsO5s+ctD3+eugPft/PAD94ZlqYX2cgdM+Q5ka3zR8nnoWsmyqs0jlOrZduMM+uTAbOHJ+NvWljIe3Qy5d5VxW1nNkg8Go1Nc/rD65KhayeVhI09OE/SAZ6dScNUqYy/cWGaD51aRDa9OEKc9uAakQx5INyWsa0iWI1LXiofpd/ktnOvQ9KOx36kNWLbtJK4mv+EI4slDq/DN0xOphU6iG6ffHyllHXsoflpmEjvXMfx+A5Sqf7B19eEWxcn7UeWSH3zedzheVI/1MGkQmemnDzFavDiscn0R9Ylg5eMKUkPAVM/HC91Rdk5Z+Sjghi+aUp6PjjWciLjHKVpProuFRnPDyU+UK5BC8eULSNLobMfYvYXxbbl4wv7jZb3PCyZ+Hrso/fOyohs7LVzkmHrinXEsUuZCkIjHd7Tfsnbnjs9bzadkjKEyGpPWzeJjAY07rp50ihpPDq64r02HBrmmEJDYoRA56GR64iEUQoytGnSYWhU2lFobHSufpPakpYxrfJE8LGH5kkjG1LoFHQAGjplQVaIDEnQOBkRpA23EI/86TR8ZqltysIVvCR/OndhZEk5hq8vHgOyojOosC16TFzt2Y/jmXx0ebqd8nB1H2WOk/oatLhUIIrvIJXqX9IqlJOnrpMPwpFyFMpEfUvdaf0U6o6LAAKQEaNIpCgDC6PZlnGtxbpfMV7EgPQJ4wJBWtSr1tuYA3PLimzi7UukTIx2yEtFRny94NE2aD++jBwzxzFg5jBpI1zIbBkZBSIiJMe5IYw0qQfee5Ep/aYOkVEY72ljA+cUL2KMYDkme+70vPk0FH+eugPft/PAD94ZlqYXGR1XRxY0RBqwNHQztaShMhpRkenQHvJEZkcYPEV80t2fikEa27mr5ejCNqYMadzds0pExhVdtzEyo2Ozr4bRWb3ISJfjUPEwiuR4yJfjYKRg4zNyGXlNMS4deuTWaSIU3U4HppwIQcPoRIMWZKUIvoNUqn/Js1Bf1DHl4vgQjuRbqG/yRRaZfc5deMpNwRmRIAREwoWCcjPS0e2UmwuLfqb+yomMCxllUlmqyBjNIRMuOrSF8dfPz5SRNEmDiwrnUEeXFmSm0uEixvGMOTBHzhNS8vE5nwgTifOZY+DcSlqF9iLn2Jw7PW8+HcWfp+7A9+088IN3hqXpRTb+hoXJlBMr06E9ja9/YWpWSWR0fN0fkTE1sGl6kdlRF5+5CjOq8iMy2XaiODKpJLJxNyyQz3TIsiOyQqekw/GKqBkVIFPg6k8HJT8dUdEZdcqJoFR8/Sa2yfSKMPJlOk0cuYdT6Gh26mXxHaRS/Ut5y0zFgfpmlMJxIBdGO9Q99YLAxh2eL6MlwnUfpuOIkPjU65BVRZG137IojZOOyOYV601GbGVE5o9PRYYgte64QI27fkGmjEx3VbS0D6Z8Ni1GUIwSpz2wVsRE+9NzBCqyQYvGpNNj4nK7QNOgrTA6lGPYNVPah547e95svhZ/nroD37fzwA/eGZamFxmNhKs3J58OpaOOrMjmSceiAVuR0YD81bPYMYtTD6X95kXSAbiKIgRtnGxDXLLt3H0y7g+pyLiiaxo0VKa+TFFppGyT6YW7R6bfvjLt0GmooqMoGjidlfeMOjhe8tbpNPfKCAMdMXLclJPjtdNMj+8gleofytUX6M1+RjsyVS/UnQqJ6Tadn321MwMdWO9fUV5GJ15kgJDknHOf65Eiui1fZMtkv+JN9w2yL6My0ilXRpUe5eCiYNNiVMe0n3bA+fZfCJEmr5SDi518GVOod7n/d240qffFil/KbEzvFeq5syP9cvjz1B34vp0HfvDOsDS9yBTk4IVQa2isKkcPncZ3nDxo2HRi7pfYkURHEIGf+HSKCowSfBxfXkYEOvXLw3eQaur/fFA3vrPnocehX4z47Wma1OGkUsFUC6N2rQeVVLky2tFiZ0BGfDvpwy3+vEGl41b8eeoOfN/OAz94Z1hCZA0I36BylWdaVe5byGpgRKNTq1rjO8ilVv8XE/+NbC3x56k78H07D/zgnWFpDpHFn5YvKv7PyFH/9Yk/T92B79t54AfvDEtTiCyWkbl4lFseJuq//ih3nroD37fzwA/eGZamEBmLyMnCf9GZLijUL/XsF+2L+q8v8s5Td+D7dh74wTvD0hQig1gh9gIjP/PIX3k0VoitHyqdp4uN79t54AfvDEvTiCwIgvrD9+088IN3hiVEFgRBt+H7dh74wTvDEiILgqDb8H07D/zgnWFpGpHFPbKuU0/3VoJLA9+388AP3hmWphBZfGtWG+rp267g0sD37Tzwg3eGpSlEFr9jqh318vuj4NLA9+088IN3hqUpRBa/LK8t9fCL8ODSwPftPPCDd4alOUS2LERWS6hPX8dB0Bl8384DP3hnWEJkQYcJkQW1wvftPPCDd4YlRBZ0mBBZUCt8384DP3hnWEJkQYcJkQW1wvftPPCDd4al6UUmSymbVVhZhVNWYZ3cVvabTr/8tIUF7uzKoqzcqavHskzxMLfccR6sya8rtVaDrA//xEbJnyf8+MX9gNViZbXSQjn0CUIsvsd7VhklDivVypOUCq88QMOnoYTIglrh+3Ye+ME7wxIicyJjmWI6Mh2cB0b0nzpUFjFkKWSWJi4uL1xcvphXfUSb7o/keMISy03zXh4NVhAbQmMlUZZdto8r4+EQusQ1S24jIUSm6Xuhydru5qEi+lgxXWAR+fqVZtlHHwWHyNqPLC77aDdd7lmXULZpWEJkQa3wfTsP/OCdYQmROZEhCYTCevqsGT9s4xTp4AgN6eQ9ok3350GuPBwEYfHK/kNWt6fr/DPSEdmce1wZS1WTJ7JBLjziDZEhVJ6Igyh9mUkXWVIu+3R01q73zw8A+yg4REYZyj3aTeWljxbz6SghsqBW+L6dB37wzrCEyJzIkATPM1SRMbrhSUtIg6fb+KmlPtlIP/MgD2SBgGSKWhiFIRIeYCLpH55X8rgy9i2+3yCvSA6RMfrjmYz2QbkWeXrSuaWqkSzwnumifQq4fxQc4mWUWO7RbvpQC320mM9TCZEFtcL37Tzwg3eGJUTm75EVOrA8pPacyHi6D09Kkg4vj16rLDKdRiIpffCE3HdbMkZGT/KoLvO4Mh4uwf04RmSIjOca6j2yPJHxeDEeIcYThHgAiT4KjDQACfLACp6b6B8Fh6xG751d9tFuPF6MME3P56uEyIJa4ft2HvjBO8MSIiuIDEEhGOSjT+ZWkTFCkieGn3vIat4j2myaPBRk8rEV6Wcd3dhHlenjynjMHPkiJcQmD22tIDIkyOPDeE+cEVumyiiMeHoMxWnqPBkZ2n0ZdVE2iV/m0W4iafdosXKEyIJa4ft2HvjBO8PS9CKrlnKP3Oos9nFl8loQHCMrH6+j6AN1ec+0k+cb+jgl8cs82q2a4wyRBbXC9+088IN3hiVEFnSYEFlQK3zfzgM/eGdYmkNk8afxmhJ/Gg9qhe/beeAH7wxLU4gslvGpHbGMT1BLfN/OAz94Z1iaQmSxsGJtiIUVg1rj+3Ye+ME7w9IUIoNY6rrrxFLXQa3xfTsP/OCdYWkakQVBUH/4vp0HfvDOsITIgiDoNnzfzgM/eGdYQmRBEHQbvm/ngR+8MywNKbIBs+NbsyBodHoN75vp23ngB+8MS0OKrGXCoEylBEHQWPAvFN+388AP3hmWhhRZj0F9MpUSBEFjwS0i37fzwA/eGZaGFBlgc18xQRA0Bvr/Yt+v88AP3hmWhhUZNg+ZBUHjQb+l/17Zr2emX+eBH7wzLA0rsh6DeofMgqDBUInRf32frgR+8M6wNKzILNwz4wsAvs2kkoIgqB/ol/RP+qnvu9WCH7wzLJeEyIIguLTBD94ZlhBZEAR1D37wzrCEyIIgqHvwg3eGJUQWBEHdgx+8MywhsiAI6h784J1hCZEFQVD34AfvDEuILAiCugc/eGdYQmRBENQ9+ME7wxIiC4Kg7sEP3hmWEFkQBHUPfvDOsITIgiCoe/CDd4YlRBYEQd2DH7wzLCGyIAjqHvzgnWFpSJH96c9/St//9Gc/TT755JNkzLix8nn33t3Jnr17MvtU4tqDB5Knn3k6E17P/OpXv8qEKfZ4pk6fJvWza8+uTLyu8Oc//zl5+ZWXM+G1hHKPGDUiE95sdKauf/f730n9wY9+9KPkyp5XZeI0EvjBO8PSkCL76KOP5LVnn17JX/7yFzlZt91xu4RxwvsO6JfZpxKvvf5a8vGfPpVjI7B1+9ZMmGKPp6V/3+TGm29KRowemYnXFTrTuTqKiKzG5W5EOlPX//Zv/5YsW7EsOf3A/VKP+w9cm4nTSOAH7wxLQ4rs+L0nkklTJyebt26Rk/T73/8+ee/992XbL3/5S+m83/nOd1LJMWrjyn7k9tuS9z/4QMJ//q8/T2bPnSMnWuP98Y9/TPNgJPPxxx8n3/7Ot2UbYiAf4iIK4vQb2D957733pNF88K0PkoGDWtP9iEPcw9cflobI+3fffTfp1ad0Qbk33nwzfU/Zn3/hBUmDERf7nH3jjeTyq66Qsv/6179OvvXht6Q8H333u7IPDZRyE8ZIlbqxxzN+wngpz/qNGyqW9+wbZyX8usPXSbqM4DRdyn/LrbeUlJswyqvHRlqEP/X0U1IOOS9/+H1y9do1kpeWidFB6+Bi3EfPPFpSLxwn9UEYZckT2ZnHzsg2zuGsObMljPp66+235Fiee+H5kvjTZ06X8BtuulE+63uO/Wc//5nkx3EwiuWCyHnWfal/2gxx7TnV7ZSb47PH5tuftr3f/u63yY9//GMJo+4eefQRaVd33n2XpPW1V19NfvKTnyS/+e1vJA7tk3ArMuqMz1pnmr+vX9Im/oZNGyVcL/SNCn7wzrA0pMgmTJ4oJ/+rL31VOssLL74oDaJ33z5y0u49eVJeaTzrNqyXk0zjv//BB5JXvva1ZPuOa85J4qx0dKRA56Ozax7zFsxLGwbCZDsjG0RDOFNZbdh0Cl7ffOvNdD86IpK8+567hR27dkrYy6+8UnIs7EdjXLJsqezHSItOQH7Hjh+XMK6slJ33yOzosaPp1JJGTWdcvnJ58vY7b0t69ngmT50i+yEmLe/B6w5lyovsqSumJKRLPr/4xS+SxUuXSHrUsy23CuzkfSelXkgbYZAW7zke0qD+CLv5lptTqZ84eW+y79r9Em7rhXoi7MzjjyWHDh+S915kTJsJ17IiHQRIGqStFzc/JSUekuA924cMHypiIZzOrnLUetb9vv+D70v9Uk96TtsnTUi363HYY/PtT9seYbRV6ov3CJX60QuoXqQQ2pZtW6V8WteITPOinrTONMzXL/txPvhM+nrxaFTwg3eGpSFFBlyR6MzfPPtN6bCcTOTGK/cDaAhclRipEfbil1+UxsR0lP1p1DRQ3pebWmoH13tLP/jhD+R14eJFEk7jp4EgA02DRqP70ZgJZwRE3qAdx+ZDXDot29mfTsnIiUb5Lz8t3v/jWLQjMDJgPxUZQk2lXkibOPZ4rMgqlZd7i1oeXhmF8J4yPPPsMzICtuVmXx0VAqKj7PMXLUjuO3Vf8vrXX5fOxqiJdIiPaA/fcL3Eo16Qra0X8rTCZD8vMs671qFKjWO0FwnCEIjd7/Enn5BwBMa5HDV2tHxGABqHclQSmZ5Ty8w5syS+PTbf/rTtEa9H7+I69ZSXc/DQww+n+SEye/9Xy6siK1dnmr+vX/Zn9Ec78FJvRPCDd4alYUXGieMEMrWicTA64ApHA2H4zTYkd8/Re2SbNibdXxso7yuJbNOWzfL5e9//nrzOXzhfwhEZ++g086WXX5JGpvsxMiCc0dVzzz+X8sBDD5bkw6iC6SsdWNPiKk1aOkqwItP9EBn3AonHyIeO+s6770icPJFVKq8ep+ZBZ2TkwHSNeNShLTf1r2kBdb96zdWy/3e/9z0pL9MnRMbIgCmnfjFDp6ReSMPWC/XAsWiaxPUiYxqlI5Vrdu6QOEwvOe+MlnU/LzLSIZw4TJ8Z1fMZGWoc6lTr+YoeV0oY50JFpufUw/HZY/Ptz4pM96G8TIE5bg1HZHpsehxcqFRk5epM8/f1Szh1z+jWl7cRwQ/eGZaGFRknDBi98Pkn//Iv8pmTzRUXMXCvYu36tenJzRMZQ3ka1tjx49LtvoOXExmdik7OvQwdofj9Tp0+JR2cjsRUjX3scTz2xOPpsTCNI4yyICXdxvTLdwQ63aIliyWMKQzHyjHx2R6PFZmWd/qsGbnl1TwYvVGP1C/3V2zewP6kxYgAkVDvDz70kMRjuk4HRJyUkzBkTBk5L9Ql9UK4rZfT959Oy8pIRLfbfJlWE97aNkhGi5QB6Z5PZKD3p3RURPno7OS1d9/etB54ZfrNKJR0VWRaRxZERXx7bL79aduzdZgnMt5zcR48tE3qmHAVmdYZ7UnrTPP39UudsA/H4cvciOAH7wxLQ4uMK75+1k7PNIvhNe+Bhq43rZ986sk0PidbRUbD0fi6fc68ufIZYWl8XrXjE870hDLwmZEEHdjvR6fRtCkHErHHQYdnm51yvvraqxLG1ZmRENv02yeNgyBIW/MHncbZ41GRIcNqyqt5UI96AxmY1thy07l0KgtMeYH61jDy4NWWkf3oiJSdb58J03rhXiES0LjgRcZIiekl28iLDky4ikGPoZzIuJepxwfE0ZE9IAbSRxJ81rqnnVBPWkcW7j3p8emx+fbHK23P5i3lLYyqrOB0ask2wpAr4SqycnVm87dloC75rLcSGh384J1haViRBUFH0GkXo1a/rV5AZJV+H9jM4AfvDEuILGgK+BKCkUo9/zCU6eSlcGP+QoAfvDMsIbIgCOoe/OCdYQmRBUFQ9+AH7wxLiCwIgroHP3hnWEJkQRDUPfjBO8MSIguCoO7BD94ZlhBZEAR1D37wzrCEyIIgqHvwg3eGJUQWBEHdgx+8MywhMsdVvXpkwoIg6F7wg3eGpSFF1j6xPRNWC/iv4NLly+SPtn1a+sjaYPzHjv8o8h9LH78SBw4dlD/x+vBy8H85XYWB/Qa0DszEGT5yhKw9ZcP4P92adWvkPeXT/x12B6wMweKKehz8kX5c+/hMvI5Cu6h2dVNbH5XCLjbVtoPuZts12zNh9QLtwDvDEiIzbNy8SV6RxpeuvDwVGZ1y2/ZtmfiV6JDI2galAhg2Yni6hIyFv654kbEyBfnwvk+/lnSV1u4AiVJuys9nxMbfgny8jkK7qFZktj4qhV1sBg0ZnAmrR0JkNaCtiyLjf3TIgEZLhyIOHQAIHzl6lCzBs78gA0ZcxLf7IyvCWVEAYXAlR2TrNqyTNA8dvk6mnQhN0502Y5oIhpUl/GiIfViskHgTp0ySuDt3ffoAENIhjPdWZKx4wDpjQ0cMk31Jm/KQD2mynVcWz+NYWJSRZW9YToeysiTNnn17JA7hxCMt9tP0fN1ZKAdQ9jXr1kqdaV2pEMrVLcfPSJJ82Ie6JL7tHPaYLaTDShS8MirWtGkTQFqkS168Ul8rVq1My0q6rAyh9VGStqkj6oWys6IG77lIab2QDue73Dn25QXy49i0DIQhb12AkiWU2M7FkXQoM2nxXs+j1pfmNWXa1LQ+2JeH6FCvmgfn1pYvr2yg9UVeXFB0qSKOW9tF75be0h6Ip3Vg09By8EpZbDnKHb/tLwwGqilntdAOvDMsl4TIWFbZi4SOTWfkpFGZrB1PPN3uGzzoiIyOw0n2IzIW8uMkIRYgXdbi4tWnRTxdKw0J9m8dIELgRLN0tV1mxoqM/Wjguo4UafDej8hYgseONpAHdWD/dEyjJR7763RVy1QOWz+sjUZ9EKZLgGudlatb8rbHYUdk5Y7ZQv0wlWc0Z0dPlJt2YTsYElJ5aRj5sHx5udGXDePipIJlBMtqv3axxGUrlpc9x/yZ25eZeHbEydpwhGmnZTlsXXWXERkd25cNqDN9z3YuOpSRsrI/C0CyjXXNWM7cli+vbLBz966ivAsCQmC2/Wi7IC17y4Q6tGloOXivx2LL4Y+f/HSZqmrLWS20A+8MyyUhMq5kVJbcqC9MCXX0wr0tttPoGV10SWSFqw8i0jg8H4DtXHl13SgL+WsjoaPqEtaE+xNbTmSaJg2kqyKTUdK5Rkd6vFLfyNWWmU4jiw4W6pArNcdKZ9cGrnVWrm7LiWzB4oVpfD1myuzPNfXDKJplyHmv01M6IXHJV/dBiHRS8pFlywtlpXycm/OJDDgmlSDHRrnsMZc7x5Rt5JhRJekibxltFvajs9Mm+az1y4hROz/HTXvi2HSaycWB/IHPnDe2U5ZKItPy2bKVO5fE5ZXznicyOYZzdUF+vu4qiazc8SMy1r8jnq3HSuWsFvb1zrBcEiIDOhInQk8GlacdiArmpNAJNH5HREYjppERRiPQ4TSNkA6dJzK9Gs2YPTMN5+Rro1DKiUxlTNl59SLjRjqNQ/PJExnxCKMcmh7bKAONsVy59fioD+67aRh1QJxydetFRocmPvVnj3nV6tWZ+lKR8Z4RrqbNKAYJkD7pEsYromN0p+ebMtCZtD5s2raO+Ew705WAOX+kp+lQxnLnuFjG0vZCPOLr/oQxLeZYKCdp6DFTfo4DseuxsA1p6XGRBiNdjY+kiaMPOlGB2PJp2cqdS9LgmLmdQZnI24qMdsEoWKeMWgc+DX3GhRdZuePnAqNT67xy+ls61cJ5886wNKTI8qBh2J9PMH3QDkLF+vidRdIqXIl8eDn8MzZl+D1zeiaehyspZadzIA6/vSOQFvexND0N00epWahDoPGp2BlN+i8uOlK39piZOpVbabWEQt2Svg/zdcnaYjpiqJbR48ak7/UYaTP+GPw5zjsH5G/XODtfmahLv12Otcr2lGLilzuXCEgl5I/Ng9D0gSUdxR+/53x5Vwt+8M6wXFIiq3e4OslopIpGy70W4iIB2/k6A2lx1dT0CJNRbYVycAW3j8frCvaYGR0yLfJxLgbc92OUoZ8ZxZ5Xqufo6jm4kJzvXF4K4AfvDEuI7CKiV8hq8VfuLnHuXkYmvIlgBBk/eG5M8IN3hiVEFgRB3YMfvDMsIbIgCOoe/OCdYQmRBUFQ9+AH7wxLiCwIgroHP3hnWEJkQRDUPfjBO8MSIguCoO7BD94ZlhBZEAR1D37wzrCEyIIgqHvwg3eGJUQWBEHdgx+8MywhsiAI6h784J1hCZEFQVD34AfvDEvDi6xlXGvSfuuiZN5L1yRLv30oCDLQNmgjtBXffqqB/6iypBB/vg86B+uqUYed/b8vfvDOsDS0yIZcPSHTaIOgEmMPdewhMqwNRydslHX36xUWTKAOqUuWcvLbzwd+8M6wNKzIppxYmWmkQVANvi3lwaKZ8iCaMtuCzkOd6grD1YIfvDMsDSsy3ziDoFqqGZUxEguJXTio246MzPCDd4alIUXGvQ7fOIOgI1S6X8Z9HF0rP7hwdKSO8YN3hqUhRRY39oOuQhvy7Uqhg3V0Ecyg43SkjvGDd4alIUXmG2UQdAbfrhS+ZfNhQfeCH7wzLCGyoGnx7UoJkdUf+ME7wxIiC5oW366UEFn9gR+8MywhsqBp8e1KCZHVH/jBO8PS1CJb8sGBTFjQPPh2pVxskdlnhAblwQ/eGZamE9mcr12TXLlkSPLfL/u75L999m+T/916WTLspjmZeMGlj29XSmdExg88n3v+uRKefubp5Mjtt2XiWk4/cL/E3b7jGnmdPXdOJk6tub+QJ68zZs+Up8D77XkcvuH6dN+LDX7wzrA0ncj+cfSV8jrxodXJ5yf0kvej714kUpv2zMZMfMtl0/pKPF57rBiWMunRNcmgfVOTeV/fmdknjwVv7JG0fHijsfCtfXLsPtzyxVn95VjnvFr82cywm2Yngw9Oz8S72Ph2pXRGZDzAFxGNax9fEv7wIw+n2x959BGJc+bxx5KZc2YlY8aNTYXHk9gff/IJeRL8oiWLk/sffEC2PfPsM8nyVSskDR5sfPzeE6n4fBmAJ8Lfd+q+5Nnnni1K9MrLkxtvvkke0Ez4mcfOJHfdfZfsTxzSeurpp0qOQctHmN13z949si/hHCfxVNq+HLUGP3hnWJpOZMNvmSsS679jgnQu3hP+mVFXJK17pmTiW1RkEx5cldn2D8MvT2a8sDnpt61d3rcdmpH8rz6fS/7HP/99GmfUnQtlBPg/e3wmadk8rqzIvjh7QPJ/Z/RLWjaOlXQmP7ZWPhMX8c59bYfE6799QvJ3/b8g6bMPI03CyX/4rXMljyHXz5T4/zxnoMT7P0P/ORl5+/yS/MaeWCr5DL1hVnocpL3o3f1JrzUjZT/y/vvBX5TtX5jcJ7l8/iCpP7ZNfHi17MM26uUzI6+Q+Gy7cumQZOHb++SzpjH+1HIp7z+OvqricYw5viQZdO1UKTP7XrG4LVn83rVCj5XDJexz43sm05/flKnDavHtSumKyHhCO09T5/OmLZsljGkjskBCjILuLMgAiQwe2ibb16xbm/RvHSDv58ybm6xec3U6OmPEpqI5euyoyI44eaO3Eyfvlfibt26ROLyyH+8R6boN62RURfkIf/KpJ0WUWkZbvt4tvUv2veGmG9MR2UMPP5ycOXNGyrBl29ZkxOiRmbLUEvzgnWFpKpFxT6z99AoRgnYulRmS6rtpXGYfi4qMDjpw9yRBBUD41KfWS4fTdDUfZDL92Y1pB6cjIho++zzo1NrpNZ3Pju2Rfu6zfkyaH9K4fOHgND7Hp/mTDyMf3e+q5UNFrD7P2a9sT/PQdBHugJ0T5T1yYfQk+314KC235oG8eL/wnaKwCBt8YFpy2fRiXTFt12Ni9DqtUA/6udJxDL9ljny252r0PYskPd4P3DM53dfXYbX4dqV0RWSeR888msydP0/eM/3kbznDRgwXUaxdv1bC9YehXmSE6b6XX3WFvLIPaTBi09GRgoyIs3L1Kvm8YdPGZPnK5SIjRn16H05ltGvPLpGRzceXz+5rRYa8xk8Yn1zZ8yoZQU6fNSNTJ7UEP3hnWJpKZNB3c1FWyEs7E/xtz39MRhyZl4lvUZFZ6JRs470VmY58GA0x9ey3vV3CR9xWzIORls1f0U6O/HhFDIvfP5DMfHGLfEYQxCOcURPvEQTbJj60SvLvuWp4suTDg0n7/SslnJHVzK9sTcYcXVw2T0ZUhOt0l1f2ZfQ67xu7ZNQj+RVGQyoyPb45rxbLOf/sbomP2Ni/75biiJORm59aWpHlHQciQ76EDzk8U8KRlwqW8o2/b7m8+uOpFt+ulK6IDBEx0hoyfGg6IqPTe8HB/gPX5ooMeRDGVJNw/pvo93/goQdLyqBx/OgIGd178mT6uZzIypWR8tl9rcgQpE4tGcmFyM7RdpFERifgnhjvdVrJzX866KJ3ih0qDxUZHWvy42sFva9GuBUZIw/CESedmzwIn/5ccSqkIxifhx+tMBXlPULhM2VAFF+Y2Dvdh5EX2xAJ+U95Yp2EM1ok3OPzbN07RcIR+T9NaZGwqU9vyIxcrcgQJfFUZHxmWmtHbFBJZJWOA5FRz4QjLE2LNFS8wKjYH0+1+HaldEVk/h4ZnXzp8mWyjXtcTNeAe1CtbYOqFhlxeGXqx/7tkyZk8uLbT43DZ6aVTFuRkR29lRNZWkZXPruviqxH754Sl5v/xOU+XIjsHG0XSWT9to6XDsA9MaTASIzOx3SPKZGPb6l0j4xwKzJGUIT3LeRHfO55EU6nJHzWV7fKZ59ONSJj6qXhMGBHcZQy7uQyyV/z1hEYIx3CgKm1z5N7e8SjHobeOFvC9F7X6EIa88/ukXtVKjJ7309Fxr0vKV9hxEh6Y44V87Yim/1KqcgqHQciA8Ips6Y148XNMprV6S5QN/6YqsG3K6WWIuNmPzfg2bZ3/z7p9PMWFKdxOoKqRmS85z7VqdOnJP4zzzwj97t8OR574nGZdk6cMkn2m79oQa7Idu7elTzx5JMiQC2jL185kTHa1LQJ57jK3a+rJfjBO8PSdCKDqU+ulxv73BNjFMJIDImpQPLoish0msc9IASj95B8OtWITLeRNlM8xAIIx4pM90E+SEGnez5PIB+2ISY+6/00jokvBHhPPZEW6H4qslF3LpBXLgjkr/LiZv6X5rbKe6a4iMgfY7njyBOZfkli0znfSDoP366UWoqMm++8ct9KvyXkm0iR2hVFeVmRIYRVV68uKzLSRjx85osDXwaYPHWKjALJi5v2hHmRnb7/tLwyiiItTZ8y+vJ5kem+CE335cY/5fJlqSX4wTvD0pQi6064H9TZEYSHbwSr/ckHeS7u4A+A+WnF3Nd3ptPI80E87u1Rrsy2bx2U6XS5tDpyHArfbnLv0Id3BN+ulM6ILLiw4AfvDEuILGhafLtSQmT1B37wzrCEyIKmxbcrJURWf+AH7wxLiCxoWny7UkJk9Qd+8M6whMiCpsW3KyVEVn/gB+8MS0OKLJa6DrpKLHXd/XSkjvGDd4alIUXGw1Z9wwyCjkAb8u1K4fdT8RzLC09H6hg/eGdYGlJk4BtmEFRLNY+D4z+H8Ti4Cwd125H6xQ/eGZaGFVk8oDfoLL4t5REP6L0wxAN6HVxZfSMNgkpUMxqzMDLjnllHpkFBFu6HUYfUZWcuDvjBO8PS0CIDHrTK/Y74AiDIg7ZBG6n0UN5K8MBeOh/fZgadQwVGXfr6rQb84J1haXiRBUFw6YMfvDMsIbIgCOoe/OCdYakbkQ0c1CrrHPkDCIKgucEL+ME7w1I3Ivv8ZV8Q64bMgiCw4AX84J1hqRuRgZrXH0gQBM0Jiz7iBe8KT12JDFgOmML7AwqCoLlgUIMPvCPKUXciAwzcFtPMIGhKdGZWzUhMqUuRAXNiDqatILQgCJoH+j2/N/NOqETdiiwIgqBaQmRBEDQ8IbIgCBqeEFkQBA1PiCwIgoYnRBYEQcPz/wEVImXTtrToRAAAAABJRU5ErkJggg==>

[image2]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAPMAAADGCAYAAAAHQbYhAAAlHklEQVR4Xu2d+ZsURbqoz99xn3ufc+c885xR0ZFd1mZvmrXZd2RHaLZmb1bZGgFBUAFBFkVA9n1TQEVFREEYXFCZc+5x5sw4c5zn/A1x6/2aqJP1ZVVX9WJ3ZtX3w/tkRWRkZGRmvBlRVRGZ//S///n/OMMw4s8/6QjDMOKJyWy43/zuCdeqx2DXts9oo4Fo0qpj6Dpofvdsq9B2mWjRtdRkLnSatC6SyvB0m87uiWatjQaiVffB1QrdrKi3pNHbZYLrZzIXMIisK4XRcHAT1dcEaJF12lwwmQsUutZUJl0hjIYjk8x0mXXaXDCZCxS+I1vXunHJJHNtb7Imc4FS2wpj1B8ms1Ev1LbCGPVHNpmfatXRDSzfKp8HzN7ixq07JXE6H4/JXKCYzI1PNplhxfn/dkVDXpDl5C3vhfIIYjIXKCZz45OLzMtO/90tPvqTW37mF9e8az83a/eXbumpn12vSSsS6352xeMWSbr+MzaYzIVKLjL/8OiPbvnqymR42pz57tjJ06F0ubBs9Tp39959+Txn0dLQ+uL+g933Pz5Kidu2c7cbMW6yO3vxkjtay/3mQqa82T/LP3zzTdoy15VcZIaK43+W5aw9d9zc/Q9c0aCp0lJDnymr3BMt2rjB8143mQsVXWHSgcw3b91Oht+7/kG9yNyuW0lofUnpkJDMd76671asqXQDRz7v+g0ZGdqmvsiUN/tnOblsdtoy15VcZV5w6I+ynLjhvLTGI5buS8o8fv0ZaZ1N5gJGV5h0IPKHH38qnzds3uq+uHtXZO7Wd4CEm7Xr5E6cOeuatGrnHn7/o5tXsdytXLve9R483PUaONR98+3DZF66ZSYdknbvN0jSITM3j1ZF3dy1j264tl2L3b0HD9yWV7cnW2bW7ztwUNJQLsqxeMVqCX/0SVU5Pbe++FKWW7fvdJ8nPrPtlJnlIujufW+7gSPGyvFNmDZT8u7au1TSPPtcR0nj90/evmXmZjN28jR3+85dd/WDDyX/T2997lp16i7Hz9IfA+dKn09NrjJrnmrVPvm5Wafe7nfNn5PPJnOBkq3CAJV9wdIV8pnKicDIvHbj5mSaZ1p3cENGj5PKTPjS+9fc6XMXhHv3HyTTaZmvXL2eXLf37YNJmQmv2fCyLH3LHJSZGwfrEKpy05ZkHuNfmJn8HMwDkUlH67v+5VdEyAOHj4jMHXr0ljTk/WRCCNKcOH0u2UPwLbOX+cyFSxIum7vQPXycZmbiM0tf9vsPvnbHTp2RNMHypKO2MmfCZC5QcqkwyPxk4vtYxYtrpII3b99ZZEZqnwYJRk2YnJSZrviO3XuT+HRaZt+ywf53DqV0szPJHOyGI/Omra8lw3SF/Weg1zBualmy3CxPnr0gLamX2aclb25IpFm1fqOk8ftn6WVGdMKTEvvyZfE3ES9z07ZF7vzlK6GvDOkwmY16IZcK478vU1Gnly+Qz/7HIiorAnuJ/ZKWU9Yl+CzwfXvpqnVJOeYsqHBPt27/P+luf5ki8+qXqmQ+fvqs7BuZ3z1+MkWQz7+8U7XfRBzxH9/8LKXsvtzli6t+uPJl5ZhIP2rClGQ68uarAeu/e/iDpKGrzP7f2LOvSuZEmelNsC2tL+nZVst8+f3r7tuH3yfPR3VkktnGZhs1IheZq4MWu1PPfqF4oFXk+6OOD4IEiE/LHuxy14Si4j5SDm4MwS53OtgX34v53L57+h+zfHl0fBBaXh2n4bs85dLxmkwyQ9OiXqH02TCZC5S6ylwfzFqw2JUOr1s56PKCjo8D1ckMNp/ZyIkoyFzoZJO5ppjMBYrJ3PiYzEa9YDI3PiazUS+YzI2PyWzUC8+07VqjZ0wZ9Qu/VnMN9HWpCyZzgWKPDWpcOPdcA31d6oLJXODU5v9Mo/bwqCZ6RPo61Acmc4Fjj9ptODjHnGvOub4O9YHJbNhD8BsIznF9d62DmMyGkSeYzIaRJ5jMhpEnmMyGkSeYzIaRJ5jMhpEnmMyGkSeEZG7Srbl7pldr99sWT+TEv7Z/xj3VtZn753/9TShzz9PPPuOeafp798RTTxiGUQuatWzu2hd1EI+0XxllRkwtbC5wE9B5eSiELpxhGDUHqbVfaWV+uqRlSNIgz99a6bqsGBKKB1pottc7MJkNo37Bp9/89l9CnqXI3HRg25Ck0HxEkSt9Z5r7X0/8X9dhcamEdRpge70Dk9kw6pfn2rZxzzZrGvIsJ5n7vfWCazKgjcgMhNO10CazYfz68L0ZobVn1crsW+PqMJkNo+HBKe2ZyWwYMaTOMo/+cKnrsXmMyWwYjUydZebX7JaTu5vMhtHI1Fnm58pK3KjrFSazYTQyNZaZX6xpjYPyevh1m3X1IfOoMaPdpzc/dU80efJ/SJOuJmx7dVtK+IcffnA//cdP7uHDh7IkrmPnIvfLL/9wlesrJbxn716BuFWrV4XyrI6Jkye58nlzQ/HZ+PiTT0JxtWHsuOdlyXls276tu3Hjhhs5ZlQoXU3o27+fK+nTKxQfxO/Xc/2D63K9R4weGUoLR48dDcXJtU+TV33COdFxQdj3Rzc+CsVHlRrL7OGvKP5f9iITptXW6eoscyBu5uxZ7oMPP3DvX33fDR46ROLWVq6T5aXLl6SyvHPooFwAvy0X7JNPP5WKfOW9Kyn5/enPf5L4Y8ePJWT9ReL+8OBBiszQqk1r9+FHH6Zs27xVC9nm559/dm8feNtVvrRe8mPbv/7lr5KG/X117yt3+/ZtSfv1N1+7Nu3ayDq2I+3Q4cMk/ML0FyT86I+PkjL/+T//LNtx0yF86PAhSfPTTz+50WPHJMty4OA7sqTydeneVT7PX7jAnTt/XsrNueA44ey5s3I+Vq1Zndx+8tQpyZvl7PI57vfNnnXHT5yQ7U6fOe0qllTIMbLt6zu2u5e3bHbTZ5RJ3uTV8rlWsj3lJnzu/LmUc4XM08qmuVOnT0mY60e6q1evun6l/UXmjz/+OHnNfJkHDR0sx7Bn3165rsQdfvewpHlj1xuyDeXkvAT3lyvjJoyTvH19kbwTx7F7z5vJ42Bdn/595VryeVHFIjle6gxpdr/5pnvy6aeS54fy6v00FLWW2UNLnGnASH3ITGsIVNTrH3wg6xjXzbr+A0rdK1tfkTgqABdnx84dyTwIB++sXLjgPv7y178IyFEl1y9uccXiFJnbdmiXFD0Iwp49e1b4+3/9l9u+Y4dsx7qS3iWy/e0vvnD/9u//JvHkz42HC3/zs5vJfFhHRffbNvn90yLF5le2uIuXLkr+3GCQlH3e/eque3PvHte6zXPJPEjPTYH0R44eEdGIRyKWwZZ50pTJrqhzp9CN8q233xKJqaCc3+Ejh0tepKPc3ERJR6Xd9eZu2ef+t/YLSPXukXeTeZXNnJGSN+Wgh/Le++/JcTRt0Uzi2Rc35WDLzDXzZfbbst5fV66nl5Aw1x+JgvvjpqHhZhBMA9xAg/smb45j3/79EuY4vOj+fHup5z7ucVEu8vfnpzHJKnO24ZzVUZfhnOla5qvXrlV9Ttw9WUdF8DJTUbnIPgyEiffhoOijxo4WgdasW+vGT5ognzXcRHbt3pUULQhynjx1MklQZm4AyOhlHjB44OPW/x8iHC21z4e4BQsXpuwDUXa+sVNaRZ8/ecKdu3ckLfn69LQor77+mkjF8SIY8elkppudTmbW0SpfvnLZLV+5QvKiJ0Q8MvvW1stM/IaNG4R1lZUpUnDDCOYdlLm4pKeMVCK+JjLrmzY3NMJ8ddIyr3hxZYgFixampAEtM3kT9nlzHF5mfwPi+nHsM2bNTO6fc6N7I41BVpl/2zwsaa7IBI3m6Z88WBuZCXMhqVxUeCoFFT24Tst87MRx99QzTaQyB1vpTl06ixS3Pr8lF4jPtP7A54OHDkmXmFaR1luXj+5zj57Fsg/E9jLTJUeIgUMGpbTM5XPLpRt+//5999r21+VGgZx/+9vfpEVkyf6Qg2MbMWqESEmLQCUrHVgq+TDSh2OlN+DLQsViG46DY/Td9KDMHG91MrMdrQvlouuKtHRzfct85uwZSedlRkR6RsRxjtlOrmniRuu7056gzPRM6Kb7ctVWZo6lQ6eOUm4tc66kk5njkAbg8XGQP2GkpayUi+OlO00Phm04Hn9+evfrE9pPQ5FVZmD2U01mTtEiM2WyuimQ2WTOBJUhGEZULqpOF6RNQmROvI4HRPJ33ZrSrbi769yti3z2MvMDEULrtHQvKasPt2jdUrrjwTRsSzfbhykbErP0cYRrW96a4PeR6bwB14Jz68P8jiDfn9OkDdK1RzfJN9hrqin0HjifdItr+sNkLqQ7juD1g+BXHU9t63V9kJPMQAvL999ckK55hha5rjJHlWA326geJKb137T55dC6XKH3Qdf22vXrWW/mDcmv+et7NnKWub5pn2cyG0Zjg1PaM5PZMGIITmnPTGbDiCE4pT0zmQ0jhuCU9sxkNowYglPas8jJnOsYWf7L5O8C/gvUf2EBf4nouHXrq4aD1hU/zNDDf5g6Ta7wPy7Hke4Y+Evm/IULKXF79+1rkL+rjGiDU9qzWMvMf4EMj9TroHtxj1AcAxl0XG0IDmeEusqs/9P0pJPZj/DSaY3CAqe0Z5GQmTHS/JfIf4gIh8zAMEkGwvMfIwMvGENMeoZd6paZyRc8F4nwhk0bRWZGErEdI8dYxxBRwnr/tLSM6mGcM6OdGCnE/6MMRyQ/BngwTpdBE4wMSiczo6WYTDBg0AAZHsmwUT86izwQk6X+nzTYMjOJguMYP3F8yjbMyGLEFkMpCTMaq7oBHkb+g1Pas0jInG7AO9vMWzBfKjEVnHUMeaQSMy1Py+zHz9KSeZl9i+e3z9Qy022dOm2qDJEkv3SD/RnLHCxvcHtk1gPyKZOfFIGkTGSQ/Td5Um4uDB9kGGdQZvIIHgcy+9lf3HAYGmotswH4oT2LhMzpBrwDkw+Y/uZlpMXzUmmZ/ewhhPQy+/yzyYxojC5auHhhUmY9Pnha2fRk+nQy6wH5LP2kCFp41ss45YTMfkIAwz6DMpMmeBzBbrbJbATBKe1ZJGSmtWXIHy2Z72azJOzn2iLMSxtekm4w29AKepkRhBbMz5tdvXZNisyIwZIbxsaXN4V+CGOKHfnQnffd7KDMz48fJ1101oGWmVa9c9fOUmbW+wkhHJcvr/7RzMPNSsb9Jo4BuTkOpOY4gjIzj5cbA/ODKStfORpzPq3RuOCU9iwSMnv0gHdm/LCUAf6Jyk73NZMUfEf1M1t69uoZWh8kXXn4Ts1SlyFIdZM4PHX5pZnJ8BwHXw/0AxIMIwh1WHsWKZmzQXdVx3mY9hfsCscVjqNdx/aheMMIglPas1jJbBhGFTilPTOZDSOG4JT2zGQ2jBiCU9ozk9kwYghOac9MZsOIITilPTOZDSOG4JT2zGQ2jBiCU9qzSMnM0yoZDcVgEaYwGkahQJ0PPq01GzilPYuUzBwUgyZ4fG3T5k0No2CgzlP/eYSx9iIdOKU9i4TM3JE4EH2AhlFoeKm1Ixqc0p5FQma61rzxQR+YYRQi9E61Ixqc0p5FQmZrlQ0jFe2IBqe0ZyazYUQQ7YgGp7RnJrNhRBDtiAantGcms2FEEO2IBqe0ZyazYUQQ7YgGp7RnJrNhRBDtiAantGfxkLlFs1T0eqMg4VluP/74ozzokccP+/jvHn4nf++w9Hzz7Teh7bPx8OHDUFw2GMlFuXR8TdGOaHBKexYPmR8zeeqUUBxkOnk8U0vHZWPM82NDcbBm3dpQXDp4uuiCRQtD8Ub90qNnsfvx0SP5/MUXX7jPbn0mIj38/qHE83BEn3bba6+6gUMGpWw/YPBASff1N19LmEcf3/r8lsTdu39P4u7cvSPPQb/71V2JP3HypMTzUEVuItCxc5HEff/995KGhzFWrq+UOG4GpGEcRTKfRNjnUx3aEQ1Oac9iKfPqNavd2sp1btiI4W7+wgXy1E4uHk/JROxVifU8oC8o84SJE+TxtpzoOXPnyHLu/HmyTeVL62U77u58Zj3bL12+TNJJmsSSfFk2a9lcykwZiCP/8rnlkgdPBjWZGwYeoUyLi0Q85piHICJ1UGaWCKS3vX//vtSny1cuy7W8/sF12Y5r/+1330oaZORxz2w/YdJEEXbkmFES5rrz9FTKwIsR2Dd14HbixkIdqVi6RB6tTP1EXp8PT1klH10ejXZEg1Pas1jKjFws1yfEY/ibb5k5gYxtJcydMCgz23AT4BG1bMebJViyDV0ytmMb3zLPnD3LLVm2VO72K198UdLymW5+n/593YurXpR0vE6Huz775A5MWpP512fQ0MEiH489Rg4eP4wsJb1LUmRGJC0zL1Hw2yIZ1w6ZvWSbNr8s2yMzn0n7hwcP5HHPrEdgn5dP4/dHzwyZab3JH7jh+HzoAfh8qkM7osEp7VksZeaEsUQwBOJi8JxswjwqlzAXW8vMGzL6lfYXqZGX9MBntmMbLzPP5ea1OTwPmy52sJtdOrDUrVq9Sj6TX1Bm7tYm868PN1PkQExaQ4Tl+ebgW2r/mWsc3JaeFeJSL5GM1ta3zJ27dZHuNekQleeX03X3NwCec862vI1kyLCh8n2d7ZGW/HjOOTK/vmO71DmeKMsLFnw+NATko49Hox3RsC/tWSxlRhy6uKPHjpEwLSjPyibOd32RSstMtxr5ENHL7LcBtundr4/IyONuyYd9USm0zFxcvx1xbMNFJD1dK112o55J9JDku2tCDERetmJ5cp1vmfn6xWfeSKK3py7Ito/F8i2zz484ZOa9X/Ld91HVd+luxd3dV/e+Sm6LnH6f8CDRglMPaBx8HNLrfHR5NNoRDU5pz2Ils2H8WiBzLpI1FNoRDU5pz0xmw0hA95pfyHV8Y6Ed0eCU9sxkNowIoh3R4JT2zGQ2jAiiHdHglPbMZDaMCKId0eCU9sxkNowIoh3R4JT2zGQ2jAiiHdHglPbMZDaMCKId0eCU9sxkNowIoh3R4JT2zGQ2jAiiHdHglPYsFjIzmWLlqqoZT356mR5vq6c7MgEiGGY2kx+LrbcFhtsFw34qY6bplUZ+w8SKe/fuyagwPwHjwddfp4yrZpw29XHHzh1Sv3QedUE7osEp7VksZJax0WurxkYzppalFpIJEcGwlpvtmTKp8/YwRTIY9jIzUF6nNfILxlF7GZnnzCQNJlssXLzQHTl6pGqsdotm7szZMykzsG5+djP5+fC7h1PyfHPvHknL+HHG+DNvmkkZPCiBOQC6DBrtiAantGexkJlJEUxJRGB/IrzMzGyaVjZd5GXQO3NLiU8ns58IwcVi3nKb9m0lP8LI7Gc/MavGT2UkzLQ6P/2R8Kw5s13FkorkYH5dXiN+MFnHT5RgSixx9AhpnZkg4V/S4Oc6e0TwQGsNCExrzkwqWvhXtr4iaZh+W/CzppjpxNhZHhhAi8nSy4zk4GX226STOdgyM4+ZJZPOeQgBMk95YapISjwztIIy++2YescMHXoLhK0bnh9Qx5CWhxUQZn401xgBkc/Xi6DMTHml9eWhF8G8eFABeR08dEjwMuMBN4qClpmnP/gpbrSQTE+sq8x+/jEi09IGW2ZaYD8vOZ3MlIebAdMurWWOP9Qb5hrTiiIac5JZfvzJJ+7subPy2d+8gzIfPXZU5kMz5ZW58D6eucxsw1c0HhXkZeZBCSdPnSxsmT2ka9G6ZSi+tmTKK9tbKJF+1JjRclx+PrORf/Bdmhu+js8VechgomHwMlPfqDM6XTq0Ixry0Z7FSuaowHdleQjC6lVpJ74bRhAvM7/F6HWZ0I5ocEp7ZjIbRgTRjmhwSntmMhtGBNGOaHBKe2YyG0YE0Y5ocEp7ZjIbRgTRjmhwSntmMhtGBNGOaHBKe2YyG0YE0Y5ocEp7ZjIbRgTRjmhwSnsWH5kb6w2QjbFPo9GRN2Xcvi0jwzZs2ihxvJmC4ZuM8CIs46wTYSZP6O3rinZEg1Pas1jIPHT4MBk26d9AQZyfChlET2OsKQy2Z2SXD/OKGj9lUsaHd+1sY7ELBIZyIrJ/a4a8niYhLsOECVNnmTVFmCGf+i2TdUU7osEp7VksZGZMtbweJtFKimyJZbqpiXoaY03RMpcnZGbJsD7GhjPZw2TOP9JNgUTcdw4dlIk9yMv4ff+OZ8LjJ01ITodkmOauN3en5GlTIDOAzLSO3AW9TLTMTHrwL5HjpXDIzEMM5MVtge4xUyRZ+qGXwemTs8vniMQ+Ty0zeTGpgllUXmb/5kg+8+ZIXwZ6EFQEtmHIJ/llG+dtRIN0UyD9y+K8fMh5/MQJiaNOcf3lfdCJeCZQ+LxsCmSaA/IgMyeOF3D5hxAgClL6Ew/ITDfct6gepqgxP9m/uTE444oW10vODCotM/v0M2K8zNyluZFQBrpXwTKQH3Ol6UlQlmzHZkQDPQWSFpqwfzkhMJuKJfLyKljqg3+Bof8eDTYFMs0BeaSbvXZtShzCcAH8i9J79e2d7Gbzus3gd2rkRS7usGwTlJkHFCA5ebANr+f02+mbgpdZv23Sl4F9tGnXRkQn7FtsI9rwQAtaU64v11OeLvKo6g2OHp5w49/iyHdlZlPxaCpZ/7i77aHbfuPGDVnHlEkvs59iqZ9Kkg7tiAantGexkDkbCKnjgnDis01ly5ZHCokuPMfELBifb2h7+xU8/0hc0+CceaBxyHStbQqkYeQZNgXSMAoY7YgGp7RnJrNhRBDtiAantGcms2FEEO2IBqe0ZyazYUQQ7YgGp7RnJrNhRBDtiAantGcms2FEEO2IBqe0ZyazYUQQ7YgGp7RnJrNhRBDtiAantGfxkTnDKBvD+DVIN59Z4nuXpAzHlCGeajhnfaAd0eCU9iwWMgenQDLxgWFy/kVeQYKvkQnCXGg/e4lx2UzWWL1mdco47HT4V+IY+U2uUyCZ5shY64uXLkpa3hTJ8E7mAugpuTYFMgNJmR+HmWLI7KYOnTrKiWLSw4jRI0VmwkyYYCqkT8+2DKbvXtxDpj1OnDxJpGZShJ8kwXa8OI7PzLLyc5jJO92DEIz8YfqMMhH20uVL0hLfv39f5KTBYAYUUjIJg+XUaVOTMjPN0U/EoC75/JgiSxzvoGIbP5zz1ue35IV0fNZl0GhHNDilPYulzMjGDCmERjakRkT96lWfntlPvOyNC8E2SIq8rGNKGq+M9bOhEJ3ZVMxH9i2zf2mYkb9km8/MJIljJ45LvJcZUaknvEk0OAXS5jOnOSBPUObSgaUyUwWZiffTDOlK67c1+s90sWmJfQtLF7tv/37SUiMyrbA8dGBJhdyNuVlwt/Yy8wACXSYjf0j3Fkje3sj3YVpXQFpu6sD0xt79+rhz58/LXGZ6gRs2bkjmZ2+BTHNAHqRFVmT0UiOzfyYXcbS+mWQG5iz7J4qUzZwhrTeSB+cmy0vYH7+QHdFN5sIg1/nMPr1vmam3fn1wRpTNZ05zQIaRD9gUSMPIE3hwhX6oQTa0Ixqc0p6ZzIYRQbQjGpzSnpnMhhFBtCManNKemcyGEUG0Ixqc0p6ZzIYRQbQjGpzSnpnMhhFBtCManNKexUbmlu3aux7DpiSYGluK+g6V44jmsU2R8umyAfGNX75UMp3LfEE7osEp7VksZPaVvU2n7rGmU58qKYKVMErHRvm0IISJ12kbG38udV3JF7QjGpzSnsVCZu7CUaxQtYHjCLaAUTs23ToT1mmiAudN15V8QTuiwSntWSxkplulL2Sc4XiiemzBskWxfBpdV/IF7YgGp7RnJnMjYDLXH7qu5AvaEQ1Oac/iLXPnHlXo+IiTs8yNcGwmczTQjmhwSnsWa5lXnP9vt/zsL8LUTRdS1nUdMDqUHpYc+1NKeMSC11LCM3d+FtomSI8hE0NxNSUXmdt17eVWnPuHsOzUz65t15JQGk3nfiOk/MPnbQ2tK9/3VUp40voTie+cQ0LpcpV58ZF/d4Omrw7F50LXAWPc0pN/FfS6niOmZb1GQXRdyRe0Ixqc0p7FWuaKo/+R/IzYRb0HJ8OZKr+uKLN23UoJZ7oJeHoMnRSKqyk5ydytt2vfo29V+sQNZPyao6E0mi79R0r5i3oNCq3TMi89+RfXbeC4ULqcZT76/2ov88CxInLx8HDePUdMz3qNgui6ki9oRzQ4pT2LtcwITKWk5Zq5/RPXtksPN//At65DcT+pMB2K+0urTdoZ22+4OXu+lJaOSk9l6jVmdqii0LJR8V/YclnC897+WvLzFW/8msOu74RFVa1lYn9z991zEyuPyzaEl53+m+szbn6yHLrMUFOZgXJzTOwDYX2vhJsLS9JzXL5l9j0M0lF2L/Pw+VWtdn3LzDmgbNxIOP55bz1ww8o3u2Vn/i43Ilpyn9bLDPoaITPHyleMTNcoiK4r+YJ2RINT2rNYyxxsmStO/MkNnlHphsxcn6wwVAykI0zFQmZ/11948IeElAtDFcXLTF6EF7zzULp+fj1ijFm21816o0qWUYt2uPK9d93IhdslTH6jl+xOliMdtZEZ+Tr2HCA3CcqHpJPXn3JTX77opm6uuvEEZQ5KG5S538RFyfj6lJlz4D9z/MPnvuLm7P7CjVy03S08/Mg9v/JAcn1QZn2Ngi1zpmsURNeVfEE7osEp7VmsZQ5+Z0autl17utKpy5MVRirI3C1SWagYVAp/AyDcZ/wCaQXKtl1P5jlz502p+INmrJMwMrNkH0tO/KfcNAgjEPkiV8cSJPtOKidysd6XIx25yuyPDfHadil2JSPLpPzIQQ+AdLN3f57cpkrmmyIz5SINdB88ISQzovkWMVPZqisfMnPufBm7lo6W46cl9mnK37wjy7LXPkzZNigz4eA1QuZs1yiIriv5gnZEg1Pas1jLnAtTNp0XEZCsuh9SskEetIzBuA49+1cbzkQuMmfC/y7gW22+Bug0MGTORrm5cQPS66ojV5nTwfHzw52Oz0bwGul12dB1JV/QjmhwSnuW9zJD+259QnGNSV1kDsL3TR0XhB6DjstGXWSuC7W9Rrqu5AvaEQ1Oac9iInM0xi7XF8ExxVE7Nj3eOWrl0+i6ki9oRzQ4pT2LhcxRG79cF2xsdv1hY7NTPYuFzBCNaYJ1I9O0vWgcm02BjBLaEQ1Oac9iI7NhFBLaEQ1Oac9MZsOIINoRDU5pz0xmw4gg2hENTmnPTGbDiCDaEQ1Oac9MZsOIINoRDU5pz0xmw4gg2hENTmnPYiMzb2zkda6k5X3MhhE3qLu8Cpa6rOu3RjuiwSntWWxk5iTok2MYcYMXuFOXdf3WaEc0OKU9i4XM/QdYi2zkD9nqe17LPHT4sNAJMYw4o+u4RjuiwSntmclsGI2AruMa7YgGp7RnJrNhNAK6jmu0Ixqc0p6ZzBHk2vXrobh0kG7jy5tC8dPKpoXizpw9kxLes3ev61bcPZQuV3r26unYf1HnTqF1mrnz58myYkmFO3/hQmh9IaLruEY7osEp7ZnJHEFykblP/75uxOiR7uq1axLu2LnIXUt8Jnzi5EmJGz9xvOR18dJFd+W9K8lt+Uz8+1ffdyPHjEoIdt699/57bvnKFSn7YDvSrVq9SsIjRo2Q/Ikv6V0i65D58LuHJX7Fiysl3dFjRyVMeTZs3CCfDx465MrnzXXHTxxPu88DBw5I+J1DB0PHmo/oOq7RjmhwSntmMkcI5NDoNJ4tr2yR5ZGjR2SJSGPHPe/69u/nzp0/L3FIS+u7bMXylLz4v57w6LFj3KXLl9zb7xyQVlPv7+Spk65Tl87u8pXLEkZirhX7DsrMzaO4pKdIO2joYNk/5ZjywlQ3c/Yst/+t/fJ3jG+Z9T65KSHykGFDJTxqzOjQ8eYbuo5rtCManNKemcwRREuVDgSj1aNVRFhaPr9u/sIFbuCQQSn5XLh4MbSPXn17yxIxiaO11GmOHT8mYvL3IOF9+/cn2OcmTJooYS8z8bT0lesr3aKKRck8uLZv7HpDPnuZ9T43bNrodr6xU8JIPa1seko58hFdxzXaEQ1Oac9M5giSTWa6okjswwixbv06kY7uNl1ZlsjF+vGTJoTyJEwLjTzbXns12SUPpvESEs960hLmOzndfC/zocOHZH+sH/P8WOlmEx42Yri0tl5UL7Pe58TJk9y2V7dJGnoTJrPJXBDQCtOdnTVndjIOIfge6r+n+h+ZZsyaKUJ7gvn4FhJxWMe2W7dtTUnjt0NOpC2bOSMZ57vZSEurz3537d4l29GNJuz3SUt9/MQJkZkueLp9mswms2HEEl3HNdoRDU5pz0xmw2gEdB3XaEc0OKU9i4XMNjbbyCey1fe8lpnva/xYo0+KYcQRZk7pOq7RjmhwSnsWC5nBpkAa+UDBT4H00ELT5eY7tGHEDequrtOZ0I5ocEp7FiuZDaNQ0I5ocEp7ZjIbRgTRjmhwSnsWCZnpPufyXCTDKARwQTuiwSntWSRkbt3mORnQrw/KMAqRth3ahRzR4JT2LBIyQ/NWLeQg9IEZRqFAi8xXTlzQfmhwSnsWGZmBA0Fo63IbhUZNRAac0p5FSmbDMHIDp7RnJrNhxBCc0p41iMzPtW0TKoxhGLXjmaa/F6e0Zw0i829++y9SAF0owzBqTvtEq4xT2rMGkRmsdTaM+oGGUfsFDSYzUIhmLZtbK20YNYTGsH2iRc4kMjSozPBss6bJghmGkRt4k65rHaTBZTYM49fBZDaMPMFkNow8wWQ2jDzh/wM+Aw9VZZl1hwAAAABJRU5ErkJggg==>

[image3]: <data:image/png;base64,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>

[image4]: <data:image/png;base64,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>

[image5]: <data:image/png;base64,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>

[image6]: <data:image/png;base64,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>
