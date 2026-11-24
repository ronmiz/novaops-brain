# NovaOps Company Brain — הסבר קוד צעד אחרי צעד (כולל ה־Flow)

> המטרה: שתוכל לקרוא את הקוד, להבין למה כל קובץ קיים, ו**לבנות את זה שוב בעצמך** לפי הסדר.
> כל הנתיבים יחסיים לשורש ה־repo: `C:\Ron\AI ENGINEER\lessons\novaops-brain`.

---

## חלק א׳ — מפת ה־repo

```
novaops-brain/
├── novaops/
│   ├── config.py          ← כל ההגדרות (.env, נתיבים, TODAY=2026-07-01, MCP host)
│   ├── llm.py             ← הדלת היחידה ל-Bedrock (chat_model / embed / converse)
│   ├── db.py              ← SQLite: reseed + כל השאילתות + כתיבות idempotent + audit
│   ├── rag/
│   │   ├── documents.py   ← קריאת 102 מסמכים, front matter, audience, חיתוך לחתיכות
│   │   ├── store.py       ← OpenSearch Serverless: יצירת אינדקס + ingest
│   │   └── retrieval.py   ← filter → k-NN → rerank → cut   (ההרשאות כאן בלבד!)
│   ├── agent/
│   │   ├── run.py         ← ask(): נקודת הכניסה היחידה לסוכן + trace של Langfuse
│   │   ├── graph.py       ← גרף LangGraph: distil→classify→scope→answer↔tools…
│   │   ├── policy.py      ← "חוקי הבית": TurnPlan, loadouts, verify_request_type, prompts
│   │   ├── memory.py      ← זיכרון מזוקק ל-5 שדות עם שם
│   │   ├── contracts.py   ← מודלים Pydantic, ציטוטים, claims_granted, decision_answer
│   │   ├── write_gate.py  ← הפונקציה היחידה שמשחררת כלי כתיבה (רק מול שורת אישור)
│   │   └── approval.py    ← תהליך Webex: gather → wait(interrupt) → release → decide
│   ├── approve.py         ← CLI לבן אדם שמאשר/דוחה
│   ├── vendor.py          ← Workflow 3 (עצמאי, בלי סוכן)
│   ├── renewal.py         ← Workflow 4 (מכונת מצבים מתמידה)
│   ├── api.py             ← FastAPI
│   └── worker.py          ← worker ל-Renewal
├── server/server.py       ← שרת MCP (FastMCP) עם כל הכלים
├── evals/                 ← golden_replay, run_submission, register_judges, retrieval_eval
├── scripts/               ← ask.py, show_trace.py, show_scores.py, check_langfuse.py
├── tests/                 ← 141 בדיקות, בלי AWS
├── docs/                  ← OBSTACLES.md, adr/0001–0009, guide/
├── Dockerfile, compose.yaml, requirements.txt
└── SUBMISSION.md
```

**שלושה חוקי ברזל** (מתוך `CLAUDE.md`):

1. כל קריאה למודל עוברת דרך `novaops/llm.py`.
2. הסוכן לא מייבא את `db.py` — רק דרך כלי MCP.
3. מודל רק **מציע**; רק קוד **רושם** שמשהו קרה.

---

## חלק ב׳ — ה־Flow המלא של שאלה אחת

```
משתמש: "Can I use my personal laptop for work?"  (E010, employee)
   │
   ▼
run.ask(message, caller_id, caller_group, thread_id)          novaops/agent/run.py
   │  פותח span "novaops-turn" ב-Langfuse (session=thread, user=caller)
   ▼
_run_turn → load_tools() (MCP client → 127.0.0.1:9880) → build_graph(tools, saver)
   │
   ▼  ─────────────── הגרף (graph.py) ───────────────
START ─(שיחה ארוכה?)→ distil ──┐
   └──────────────────────────→ classify      ← המודל ממלא TurnPlan; הקוד מאמת (verify_request_type)
                                   ▼
                                 scope        ← קוד: scope + loadout (אילו כלים לראות)
                                   ├─(בקשת גישה)→ handoff → END
                                   ▼
                                 answer  ◄────┐  המודל כותב / מבקש כלים
                                   │ route    │
                ┌──────────────┬───┴────┬─────┴──────┬────────────┐
                ▼              ▼        ▼            ▼            ▼
              tools          rearm    recite      handoff     checklist / END
         (MCP + someone_    (חפש שוב) (צטט שוב)
          else guard)
                └──────────────┴────────┘ → חזרה ל-answer
   │
   ▼  ─────────────── אחרי הגרף (run.py) ───────────────
אם יש handoff → approval.start(...)  → Webex (עוצר ומחכה לבן אדם)
only_theirs (לטקסט מודבק) → attach_sources → citation_report → decision_answer
   │
   ▼
מחזיר dict: status, answer, intent, tools_used, citations, trajectory, trace_id …
וכותב ל-span: metadata.trajectory (מה שהשופטים קוראים)
```

עכשיו כל צומת לעומק.

### שלב 0 — `run.ask()` (run.py)

- מייצר `thread_id` (אם אין) ו־`request_id`.
- `propagate_attributes(session_id=thread_id, user_id=caller_id)` → כל השיחה נראית כ־session אחד ב־Langfuse.
- `start_as_current_observation(as_type="agent", name="novaops-turn")` → **זה ה־span שהשופטים קוראים.**
- `try/except` — כישלון מוחזר כ־`status="failed"` בכנות, לא מוסתר.
- `langfuse.flush()` בסוף — תהליך קצר חייב לשלוח לפני שהוא מת.

### שלב 1 — `distil` (graph.py + memory.py)

- `should_distil`: אם יש > 12 הודעות או > 10,000 תווים מאז הזיקוק האחרון.
- המודל ממלא `ConversationMemory` עם **שדות בעלי שם** (כללים שהמשתמש קבע, נושאים סגורים...).
- `memory_is_safe(old, new)` — הקוד מוודא שהזיקוק לא "איבד" כלל קודם.
- למה? שיחה של 10 תורות: כלל מתור 1 ("SaaS freeze ב־Q3") נדרש בתור 9.

### שלב 2 — `classify` (graph.py + policy.py)

- `planner = chat_model().with_structured_output(TurnPlan)` — המודל מחזיר JSON מובנה: `current_intent`, `request_type`, `answer_quote`, `relevant_constraints`...
- **`verify_request_type`** — הקוד לא סומך על המודל:
  - `recall` + מילת "עכשיו/עדיין" (`FRESHNESS`) → הופך ל־`lookup` (צריך מידע טרי).
  - `recall` בלי ציטוט שבאמת מופיע בשיחה (`_near`) → מוחקים את הציטוט.
  - `pasted_text` עם פחות מ־3 שורות → `lookup`.
  - `action` בלי פועל של הגשה (`FILING`) → `acknowledge`.
  - `acknowledge` עם `?` → `lookup`.
- `enforce_evidence` — אם צריך ראיות ואין, מכריחים שימוש בכלים.

### שלב 3 — `scope` (graph.py + policy.py)

- `select_tools(plan, read_tools)` → בוחר **LOADOUT** לפי הנושא, למשל:
  - `policy_question` → `search_documents`, `check_software_subscription`, `list_onboarding_tasks`…
  - `employee_lookup` → `get_employee`, `check_team_system_access`, `list_onboarding_tasks`, `search_documents`.
  - `access_request` → `list_access_requests` + …
- `read_tools` **לא כולל** `WRITE_TOOLS` (`create_access_request`) ולא `APP_TOOLS` (`request_approval`, `get_approval`). המודל פשוט לא יודע שהם קיימים.
- `after_scope`: אם זו בקשת גישה → `handoff`.

### שלב 4 — `answer` ↔ `tools`

- `call_model`: המודל מקבל `ANSWER_PROMPT` (כולל "Today is 2026-07-01" וכל חוקי התשובה), חלון של 4 תורות אחרונות + זיכרון, וכלים מה־loadout בלבד.
- `run_tools`: מריץ את הכלים דרך MCP. שמירות:
  - `CALLER_TOOLS` (`search_documents`, `check_team_system_access`) — ה־`caller_id` **מוזרק ע"י הקוד**, לא ע"י המודל (אחרת אפשר להתחזות למנהל).
  - `someone_else()` — אם המודל קרא לכלי עם ה־id של השואל אבל השאלה על אדם אחר → נחסם (#28).
  - `unverified_employee_id` — id שלא הופיע בשום מקום → נחסם.

### שלב 5 — `route` (בקרת איכות)

| מצב | לאן |
|---|---|
| המודל ביקש כלים | `tools` |
| ציטוט שלא קיים בראיות, בלי כלים | `rearm` (מחזיר plan ל־lookup וחוזר ל־answer) |
| recall לא מאומת (אין ציטוט/כלי/מקור) | `rearm` (#30) |
| היו ראיות, אבל אין ציטוט / ציטוט לא נתמך | `recite` (מוסיף `CITE_REMINDER`) |
| access_request + כלי רץ + `ASKS_FOR_ACCESS` | `handoff` |
| עובד חדש | `checklist` |
| אחרת | `END` |

### שלב 6 — `checklist`

- המודל מחזיר `ChecklistProposal`; `checklist_errors` בודק כל פריט מול הראיות.
- **ניסיון חוזר אחד** עם השגיאות. לא עבר → `status="needs_human"`.

### שלב 7 — אחרי הגרף (run.py + contracts.py)

- `only_theirs` — בטקסט מודבק, משאירים רק את הפריטים של השואל.
- `attach_sources` — מצרף מקורות שהאפליקציה ראתה.
- `citation_report` — כל ציטוט בתשובה חייב להופיע בראיות (אחרת = "מומצא").
- `decision_answer` — את החלק של Webex כותב **קוד** מתוך הרשומות, לעולם לא "access granted".

---

## חלק ג׳ — Webex: תהליך האישור (approval.py)

```
handoff (graph) → AccessRequestIntent  (מי, איזו מערכת, למה)
   ▼
approval.start(app, intent, trace_id)        thread = thread_for(employee, system)
   ▼
gather   : get_employee, check_software_subscription, list_access_requests, tickets,
           request_approval (או מחזר אישור פתוח, למשל AP001)  — via mcp_caller
   ▼
wait     : interrupt({...})  ⏸  נשמר ב-var/checkpoints.db
   … הסוכן מחזיר status="pending". השיחה ממשיכה. …

בן אדם, תהליך חדש:
python -m novaops.approve AP001 --by E006 --approve --reason "IT approves"
   ▼  (approve.py → db.record_approval: רק המאשר הרשום מותר)
resume (באותו trace דרך trace_context)
   ▼
wait     : קורא שוב את שורת האישור מה-DB  (ה-payload של resume מתעלמים ממנו!)
           עדיין פתוח → עוצר שוב | נדחה → decide | אושר → release
release  : write_gate.released_writes(approval_row) → create_access_request (idempotent)
decide   : build_decision → AccessDecision  (קוד בלבד)
```

**למה זה בטוח:**

- `write_gate.py` — הפונקציה **לא מקבלת את טקסט ההודעה בכלל**. רק שורת אישור.
- השרת (`server.py`) **גם** מסרב לכתוב בלי `approval_id` מאושר — הגנה כפולה.
- `db._audit` — כל כתיבה נרשמת. מפתח טבעי → בקשה זהה לא נוצרת פעמיים.

---

## חלק ד׳ — RAG (novaops/rag/)

### Ingest (פעם אחת): `python -m novaops.rag.store`

1. `documents.load_chunks()`:
   - `parse_frontmatter` → מטא־דאטה.
   - `audience_for`: `handbook` → `all`; `manager_playbook` → `manager` **תמיד** (fail closed); שאר האוספים → בלי הגבלה.
   - `doc_date` נשלף מהמסמך.
   - ≤ 300 מילים → חתיכה אחת. ארוך → לפי `##`, וסעיף ארוך → חלונות עם חפיפה של 50 מילים.
2. `store.rebuild_index()` → `llm.embed()` (Titan V2) לכל חתיכה → OpenSearch `novaops-brain-kb` (470 חתיכות).

### Search: `retrieval.search(query, caller_id, collections)`

1. `build_filter` → `access_clauses(caller_id)` (מנהל? רואה גם `manager`) + `collections`.
2. `knn` — 20 מועמדים, **הפילטר בתוך שאילתת ה־k-NN**.
3. `rerank` — Nova מדרג (כלי מאולץ).
4. `cut` — `MIN_SCORE=0.5`, `MAX_RESULTS=8`, `PER_DOC=2`.

> המספרים נבחרו במדידה: `evals/retrieval_eval.py` + ADR 0003.

---

## חלק ה׳ — שרת MCP (server/server.py)

- `FastMCP` על `127.0.0.1:9880/mcp`.
- **כלי קריאה**: `search_documents`, `list_policies`, `get_policy`, `get_employee`, `check_software_subscription`, `list_onboarding_tasks`, `check_asset_inventory`, `list_employee_tickets`, `list_access_requests`, `check_team_system_access`.
- **כלי כתיבה**: `create_access_request` (רק עם `approval_id` מאושר).
- **כלי אפליקציה**: `request_approval`, `get_approval` (רק תהליך האישור משתמש בהם).
- `cited(rows, key)` — מוסיף לכל שורה `[record: …]` כדי שהמודל יוכל לצטט.

> **שינוי בקוד השרת = לעשות restart לשרת.**

---

## חלק ו׳ — Vendor ו־Renewal

### Vendor (`novaops/vendor.py`)

```
extract(document, source_id)
  → llm.converse(..., tool=submit_vendor_record)   (קריאה אחת, כלי מאולץ)
  → build_result(raw):  normalize_date / cost / renewal / sensitivity / bool
                        missing = [f for f in REQUIRED if record[f] is None]   ← קוד!
                        follow_up_questions (ניסוח המודל, רשימת הקוד)
                        Draft202012Validator(SCHEMA) → לא תקין = ValueError
```

### Renewal (`novaops/renewal.py`)

```
scheduled_run(as_of)        assess (חלון 90 יום, deadline) → recommend_with_model → פתיחת run → בקשת החלטה (outbox)
ingest_event(event)         internal approval / finance / security — לפי event_id (replay = no-op)
                            → preconditions → advance → compose_provider_email (outbox)
ingest_provider_reply(eml)  parse_eml → extract_with_model → to_decision → match(decision, run)
                            תואם → confirmed_awaiting_effective_date | לא → needs_human
scheduled_run(effective)    apply_due_agreements → seat_limit מתעדכן פעם אחת + התראה לחסומים
```

CLI: `python -m novaops.renewal schedule|event|reply|status`.

---

## חלק ז׳ — Langfuse, הערכות ושופטים

| קובץ | מה עושה |
|---|---|
| `run.trajectory()` | מכין "תקציר ראיות" ל־span: `calls` (5000 תווים לכלי) + `state` |
| `evals/golden_replay.py` | מריץ session מ־GOLDEN-DATASETS על DB טרי, בודק required/forbidden facts, ציטוטים, constraint carry, no_write → score `golden_pass` |
| `evals/run_submission.py` | מריץ את EVALUATION-INPUTS (33 traces עם `--optional`), score `expected_pass`, ממלא `SUBMISSION.md` |
| `evals/register_judges.py` | רושם 3 שופטים ב־Langfuse על span `novaops-turn` מסוג AGENT |
| `scripts/show_scores.py` | מציג את כל הציונים לכל תור (v3 API) |
| `scripts/show_trace.py` | מציג trace (v2 observations API — ה־legacy סגור, #21) |

---

## חלק ח׳ — איך מריצים (Git Bash, מהתחלה)

```bash
cd "/c/Ron/AI ENGINEER/lessons/novaops-brain"
export PYTHONUTF8=1
python -m pip install -r requirements.txt
python -m pytest -q                         # 141 passed, בלי AWS
python scripts/check_langfuse.py            # המפתחות עובדים
python -m novaops.rag.store                 # פעם אחת: בניית האינדקס
```

טרמינל 1 (משאירים פתוח):

```bash
cd "/c/Ron/AI ENGINEER/lessons/novaops-brain"
python server/server.py
```

טרמינל 2:

```bash
cd "/c/Ron/AI ENGINEER/lessons/novaops-brain"
python -m novaops.agent.run E010 "Can I use my personal laptop for work?"
python -m novaops.agent.run E010 "I joined Customer Success and need Webex access. Webex says my account is not licensed."
python -m novaops.approve AP001 --by E006 --approve --reason "IT approves"
python evals/golden_replay.py --session S9
python evals/run_submission.py --optional --write-submission > runs/m10-final-33-a.txt 2>&1
```

---

## חלק ט׳ — לבנות את זה שוב: סדר העבודה (Milestones)

1. **Foundation** — `config.py`, `llm.py`, `db.py` (reseed), `rag/` (documents → store → retrieval), `server/server.py`, `scripts/ask.py`. בדיקה: שאלה → תשובה עם ציטוט.
2. **Agent loop** — `policy.py` (TurnPlan + loadouts), `graph.py` (classify → scope → answer ↔ tools), `run.py` (ask יחיד), `write_gate.py`. בדיקה: `test_agent_loop`.
3. **Maya** — `memory.py` (distil), `contracts.py` (checklist, ציטוטים), `golden_replay.py`. מדידה: S1/S2/S9 × 3 ריצות.
4. **Webex** — `approval.py`, `approve.py`, כלים חדשים ב־server + `db.py` idempotent. בדיקה: pause → approve בתהליך חדש → resume = trace אחד.
5. **Observability** — Langfuse span + `trajectory` + `register_judges.py`.
6. **Vendor** → 7. **Renewal** → 9. **Packaging** (`api.py`, `worker.py`, Docker) → 10. **Submission**.

**הרגלים שעשו את ההבדל:**

- כל באג → שורה ב־`docs/OBSTACLES.md` (סימפטום, סיבה, תיקון, ראיה). יש 30.
- כל החלטה לא מובנת מאליה → ADR חדש.
- מודדים **ממוצע של 3 ריצות** — Nova משתנה ±2 תורות בין ריצות.
- כשהמודל טועה בעקביות — לא "מבקשים יפה יותר" ב־prompt בלבד, אלא מוסיפים **בדיקת קוד** (verify, route, guard).
- לעולם לא מחלישים בדיקה כדי שתעבור (`.claude/hooks/protect_tests.py` אוכף).
