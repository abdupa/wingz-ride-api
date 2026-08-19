# Build plan — 13 commits

Rules of the road: one requirement per commit, suite green at every commit, message says **why**.
Standing decisions and traps live in `CLAUDE.md`. This file tracks progress only.

Status: ⬜ not started · 🔄 in progress · ✅ done

---

## Phase 0 — before the first commit

- [x] Create the GitHub repo, so history lands there naturally rather than as one big push
- [x] `.gitignore`: `.venv/`, `.env`, `__pycache__/`, `docs/Assessment.pdf`
- [x] Decide whether `CLAUDE.md` ships in the repo (visible to reviewers — reads as discipline)

---

## The commits

### ✅ 1 — Project skeleton and custom user model
Django project, two apps (`users`, `rides`), settings, Docker Compose with `postgres:16`, pytest wired up.
`User` on `AbstractBaseUser` with `id_user` PK, `db_table="user"`, email login, custom manager with
`create_user` / `create_superuser`.

**Why first:** `AUTH_USER_MODEL` must be set before any migration runs. Getting this wrong means
dropping the database.

**Proves it:** `manage.py migrate` clean · `createsuperuser` works and sets `role="admin"`.

---

### ✅ 2 — Ride and RideEvent models
Exact fields, `db_column` on every FK, distinct `related_name`s, `related_name="events"` on RideEvent,
`default=timezone.now` on `created_at`, `Meta.ordering`, lat/lng CheckConstraints, all indexes.

**Watch:** traps 1, 2, 3, 8 in `CLAUDE.md`.

**Proves it:** a migration test asserting the real column names are `id_rider`, `id_driver`, `id_ride`.

---

### ✅ 3 — Serializers and three CRUD ViewSets
Read/write serializer split, router, `/api/` prefix. Full CRUD on all three models.

**Proves it:** CRUD tests for each model — the requirement most often left half-finished.

---

### ✅ 4 — Authentication and the admin-role gate
Token auth first, session second. Custom `IsAdminRole`. Global deny. Token endpoint `AllowAny`.
`ProtectedError` → 409.

**Proves it:** 401 / 403 / 200 tests, plus the router-walking test that every URL rejects anonymous.

---

### ✅ 5 — Pagination and filtering
`PageNumberPagination` (default 20, cap 100). FilterSet: status as ChoiceFilter, rider email via
`id_rider__email` with lowercase-at-write normalisation.

**Watch:** trap 9 — `iexact` would kill the index.

---

### ✅ 6 — Sort by pickup_time
`OrderingFilter`, index on `pickup_time`, **`id_ride` appended to every ordering**.

**Proves it:** a pagination-stability test — no row appears on two pages when timestamps tie.

---

### ✅ 7 — `todays_ride_events` and the query budget ⭐
The headline requirement. `select_related` + `Prefetch(..., to_attr=...)`, cutoff computed per request.

**Watch:** traps 4, 5, 6.

**Proves it:** query count at 5 rides and at 50 rides, asserting **3 both times**. 25 rides against
page size 20 so an N+1 would show as 23.

---

### ✅ 8 — Sort by distance (plain SQL)
Lat/lng query params, distance annotated in the database, ordering on the annotation, `distance_km`
in the response. Correct and portable — no extension yet.

**Proves it:** ordering correctness, pagination applied after sorting, and the 400s from the error table.

---

### ✅ 10 — Error handling pass
Custom exception handler, one consistent error body, every row of the error table in `CLAUDE.md`.

**Why its own commit:** a full quarter of the grade, and the criterion most candidates skip.

---

### ⬜ 11 — `seed` management command
Users across roles, rides, and events spanning several months so the report has something to report.
Deliberate edge cases: events at 23h and 25h old, tied pickup times, a ride with two pickup events.

**Note:** those edge cases are what make commits 7, 6 and 12 testable rather than assumed.

---

### ⬜ 12 — Bonus SQL report
`FILTER` aggregates, group by `d.id_user`, `LEFT(last_name, 1)`, `> INTERVAL '1 hour'`, quoted `"user"`.
A management command to run it, so the README's sample output is real.

**Proves it:** run against seed data including the double-pickup ride — the count must not inflate.

---

### 🔄 13 — README
Started early (before commit 4) rather than left to the end: it is a graded
deliverable, and leaving it last puts all its risk in the final commit. Each
commit now adds its own paragraph while the reasoning is fresh. All eight sections from
`CLAUDE.md`, including the traceability table.

**Final gate:** clone into an empty directory and follow the README literally, typing nothing that
isn't written down.

---

## Definition of done

- [ ] Every PDF bullet traced to code and a test
- [ ] Query-count test green at two data sizes
- [ ] Full CRUD on all three models
- [ ] Every error rule tested
- [ ] README followed successfully from a clean clone
- [ ] Bonus SQL in the README with real output
- [ ] History reads as a clean progression, no giant commit
- [ ] Assessment PDF **not** committed

---

### ⬜ 9 — *Optional, deferred to last:* PostGIS index optimisation

**Moved behind 10-13.** It is the only item the brief does not ask for, and everything
after it is required. Measured first at 200k rides: the distance sort is a parallel seq
scan at ~51 ms against ~0.18 ms for the indexed pickup_time sort, and it grows linearly.
The gap is real, so this is worth attempting -- but only with the required work banked.
Only if it earns its place. Switch to the `postgis/postgis` image, add a GiST expression index over
`ST_SetSRID(ST_MakePoint(pickup_longitude, pickup_latitude), 4326)::geography`, KNN `<->` ordering.
No column added to Ride. No `django.contrib.gis`.

**🚧 Gate:** `EXPLAIN ANALYZE` must show the planner actually using the index. An expression index has
to match the query expression exactly, and a subtle mismatch is silently ignored.

**If it fails:** revert, keep commit 8, and explain in the README that the production answer is a stored
geography column plus a spatial index — which the frozen-Ride rule forbids.

---
