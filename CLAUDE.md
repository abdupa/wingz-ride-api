# Wingz assessment — Django ride API

## What this is

A RESTful API built with Django REST Framework that manages ride information.
Source of truth is `docs/Assessment.pdf`. **Where this file and the PDF disagree, the PDF wins.**

Graded on four criteria of roughly equal weight: **Functionality, Code Quality, Error Handling,
Performance**. Every decision has to be explainable on video to the CEO and CTO, so the reasoning
matters as much as the code.

**The real test:** it looks like a CRUD exercise, it is a performance and judgement exam.
The spec is deliberately incomplete — it never names a database or an auth scheme, gives VARCHAR
with no lengths, never says what is nullable, defines a User table with no password while demanding
authentication, and contradicts itself between requirements 3 and 4. **The blanks are the test.**
Decide deliberately, and write down why.

---

## Decisions already made

The PDF leaves these open. These are settled — do not re-litigate mid-build, but do record each
one in the README with the alternative and why it was rejected.

| Blank in the spec | Decision | Why |
|---|---|---|
| Database | PostgreSQL in Docker Compose | "Very large table" and interval/month SQL both need a real RDBMS |
| Auth scheme | DRF `TokenAuthentication` (+ session for the browsable API) | No extra dependency, one-line curl, easy README. JWT is the production answer — say so |
| User has no password | `AbstractBaseUser` adds `password` + `last_login` | The only knowing deviation from the spec's tables. Requirement 2 is impossible without it |
| Req 3 vs req 4 contradiction | List returns `todays_ride_events` only, plus a `ride_events_url` link | Req 4 is explicit and measured; req 3 is loose wording. The link honours both |
| VARCHAR lengths | status/role 20, names 150, email 254, phone 32, description 255 | In PostgreSQL varchar(n) and text perform identically — these are validation, not speed |
| Nullability | Everything required | Simplest reading of the spec's silence; all three example statuses imply an assigned driver |
| PK size | `AutoField` (INT), matching the spec | Note in README that BigAutoField is the production choice for RideEvent |
| `status` / `role` | `TextChoices` | Buys a clean 400 on bad input. The spec's "e.g." means the list is extensible — say so |
| Report month | Month of **pickup** | A trip is counted when it started. Depends on `TIME_ZONE` — set it explicitly |
| Distance sort | Plain SQL first; indexed version only if `EXPLAIN` proves it | Correct before fast |
| Auth's query cost | Query test uses `force_authenticate`; assert **3**, the brief's number | The brief measures fetching the ride list with its relations, not authenticating. Token auth adds exactly 1 query (measured). Disclose it in the README; do not switch to JWT to game a number the brief never asks about |

---

## Schema — mirror the spec exactly

**Ride** · `db_table = "ride"`

| Spec | Django |
|---|---|
| `id_ride` INT PK | `AutoField(primary_key=True)` |
| `status` VARCHAR | `CharField(max_length=20, choices=Status)` |
| `id_rider` INT FK | `ForeignKey(User, db_column="id_rider", related_name="rides_as_rider", on_delete=PROTECT)` |
| `id_driver` INT FK | `ForeignKey(User, db_column="id_driver", related_name="rides_as_driver", on_delete=PROTECT)` |
| `pickup_latitude` FLOAT | `FloatField()` |
| `pickup_longitude` FLOAT | `FloatField()` |
| `dropoff_latitude` FLOAT | `FloatField()` |
| `dropoff_longitude` FLOAT | `FloatField()` |
| `pickup_time` DATETIME | `DateTimeField()` |

`Meta.ordering = ["id_ride"]` — **required, not style.** See traps.

**User** · `db_table = "user"`

`id_user` AutoField PK · `role` CharField(choices) · `first_name` · `last_name` ·
`email` EmailField(254, unique) · `phone_number` CharField(32)
Plus `password` and `last_login` from `AbstractBaseUser`. **No `PermissionsMixin`** — groups and
permissions are two join tables we never use. `is_active` comes free as a Python attribute, not a column.

**RideEvent** · `db_table = "ride_event"`

`id_ride_event` AutoField PK ·
`id_ride` `ForeignKey(Ride, db_column="id_ride", related_name="events", on_delete=CASCADE)` ·
`description` CharField(255) · `created_at` `DateTimeField(default=timezone.now)`

### Frozen and not frozen

- **Ride is frozen.** No new columns — especially no stored `distance`. Indexes are allowed;
  an index is not a structure change. This is the trap the assessment sets.
- **User carries only what auth requires** — `password`, `last_login`. Nothing else.
- **RideEvent stays as specified.**
- No `created_at`/`updated_at` audit columns anywhere. The reflex is strong. Resist it.

### Constraints

- **Add:** latitude within ±90, longitude within ±180 — database CheckConstraint *and* serializer
  validation for a clean 400. Physically true, so it can never reject data the spec permits.
- **Do not add:** `id_rider != id_driver`. Sensible, but the spec never says it, and rejecting
  valid input looks like a bug. Note it in the README as considered-and-declined.

### Indexes

| Table | Index | Serves |
|---|---|---|
| Ride | `pickup_time` | the time sort |
| Ride | `status` | the status filter |
| RideEvent | **`(id_ride, created_at)`** | the 24h prefetch **and** the bonus report |
| User | `email` unique, `role` | login and the email filter |

Django indexes FK columns automatically — `id_rider` and `id_driver` need nothing extra.

---

## 🔴 Traps — these fail silently

Each of these produces correct-looking output while being wrong.

1. **Django renames FK columns.** `id_rider` becomes column `id_rider_id` unless `db_column` is set.
   No error, no warning, wrong schema.
2. **Two FKs to User need distinct `related_name`.** This one at least fails loudly.
3. **`auto_now_add` on `created_at`.** Makes the field non-editable and always "now" — which makes
   the bonus report unseedable, the 24-hour boundary untestable, and RideEvent create broken.
   Use `default=timezone.now`.
4. **A serializer field that queries.** `SerializerMethodField` calling `.filter()` returns perfect
   JSON and runs one query per ride.
5. **`Prefetch` without `to_attr`.** Calling `.filter()` on a prefetched relation discards the cache
   and re-queries — so you pay for the prefetch *and* the N+1.
6. **Cutoff computed at import time.** Freezes at server start and drifts silently. Compute per request.
7. **Ordering with no unique tiebreaker.** Ties return in arbitrary order, so a row appears on two
   pages and another never appears. **Every ordering ends in `id_ride`.**
8. **No default ordering at all.** PostgreSQL makes no promise about row order; pagination becomes
   undefined. Hence `Meta.ordering`.
9. **`iexact` on email.** Compiles to `UPPER(email) = ...` and cannot use the index. Normalise email
   to lowercase at write time and match exactly instead.
10. **DRF's `IsAdminUser`.** Checks `is_staff`, not the spec's `role`. Name collision, wrong behaviour.
11. **Global permission locks out login.** The token endpoint must be `AllowAny` or nobody can ever
    authenticate.
12. **Auth class order decides 401 vs 403.** Token auth sends `WWW-Authenticate` and yields 401;
    session auth does not and yields 403. **Token first.**
13. **Joining `ride_event` twice in the report.** Inflates counts if a ride has two pickup events.
    Use `FILTER` aggregates.
14. **A query-count test with one ride** passes whether the code is right or wrong.

---

## The query budget — the only measured requirement

| # | Query | Mechanism |
|---|---|---|
| 1 | Ride page + rider + driver | `select_related("id_rider", "id_driver")` |
| 2 | Their events, last 24h only | `Prefetch(..., to_attr="todays_ride_events")` |
| 3 | Total count | the paginator |

```python
cutoff = timezone.now() - timedelta(hours=24)          # per request, inside get_queryset
Prefetch(
    "events",
    queryset=RideEvent.objects.filter(created_at__gte=cutoff).order_by("-created_at"),
    to_attr="todays_ride_events",
)
```

The serializer reads `todays_ride_events` as a plain list attribute. Nothing else.
Apply the same queryset to **retrieve**, not just list.

Known and acceptable: on a very large table the COUNT is the slowest of the three. Cursor pagination
would remove it but cannot coexist with user-chosen ordering. Say this in the README.

Ceiling worth knowing: `json_agg` in a subquery would do it in **one** query. Rejected — raw SQL in a
queryset, harder to read, and the spec's target is two. Be ready to say this on video.

---

## Authentication

Two separate jobs. Authentication = who are you (token). Authorization = are you allowed (`role == "admin"`).

- Custom `IsAdminRole` permission — **not** DRF's `IsAdminUser`.
- Set globally via `DEFAULT_PERMISSION_CLASSES` so nothing can be left open by accident.
- Token endpoint explicitly `AllowAny`.
- `TokenAuthentication` listed **first**, session second.
- Implement `create_superuser` so `manage.py createsuperuser` works and sets `role="admin"` —
  a reviewer will type it instinctively.

| Situation | Code |
|---|---|
| No credentials | 401 |
| Bad token | 401 |
| Valid token, not admin | 403 |
| Admin, object missing | 404 |

---

## Error handling — a full quarter of the grade

Every rule below gets a test.

| Request | Response |
|---|---|
| `ordering=distance` with no lat/lng | 400, naming both parameters |
| lat/lng not numeric | 400 |
| lat beyond ±90, lng beyond ±180 | 400 |
| Unknown `status` | 400, not an empty list |
| Unknown ordering field | 400 — DRF ignores these by default and returns unsorted data |
| Deleting a user who has rides | 409 — map `ProtectedError`, don't let it 500 |
| `page` past the end | 404 (DRF default — document rather than fight) |

One consistent error body shape via a custom exception handler.

---

## Testing doctrine

- **Query count at two data sizes.** 5 rides and 50 rides, asserting the same number both times.
  Three queries at one size is an observation; three at both is evidence the cost is constant.
- **Seed a full page.** 25 rides against page size 20, so an N+1 shows as 23 queries, not 3.
- **Walk the router** and assert every registered URL rejects anonymous callers. A ViewSet added
  later cannot be left unprotected without the suite going red.
- Pagination stability: assert no row appears on two pages when the sort key ties.

---

## Bonus SQL — goes in the README

Count of trips whose pickup→dropoff duration exceeded one hour, grouped by month and driver.

- Collapse events per ride with `MIN(...) FILTER (WHERE ...)` — **never** join `ride_event` twice.
- Driver renders as first name + last **initial**: `first_name || ' ' || LEFT(last_name, 1)`.
- Group by `d.id_user`, display the name — otherwise two "Chris H" drivers merge into one row.
- `> INTERVAL '1 hour'` — strictly greater.
- Quote `"user"` — reserved word in PostgreSQL.
- The sample output has gaps, so **no zero-filling**. Plain GROUP BY is correct.
- Run it against seeded data and paste real output beside it.

---

## README — graded, written as we go

They asked for "design decisions **or challenges you ran into**". That is a request for an
engineering log, not a brochure. The Traps section above is the raw material.

1. What it is, in three sentences
2. Setup a stranger can follow — clone, compose up, migrate, seed, get a token, run
3. Endpoint reference with real examples, including a distance-sorted one
4. The query-count design and how to verify it
5. Design decisions — every row of the Decisions table, with the rejected alternative
6. Challenges hit
7. The bonus SQL with real output
8. **Traceability table** — each spec bullet → where it's implemented → which test proves it

**Before submitting:** clone into an empty directory and follow the README literally, typing nothing
you did not write down.

---

## Stack

Python 3.12 · Django · DRF · django-filter · PostgreSQL via Docker Compose · pytest + pytest-django.

**Not used:** `django.contrib.gis`, GDAL, GEOS. Even the optimised distance path uses raw SQL
expressions, so the project has no system-library dependency and cannot break on the reviewer's machine.

## How to run

```
docker compose up -d
python manage.py migrate
python manage.py seed          # rides, users, and months of report-shaped events
python manage.py runserver
pytest
```

## Conventions

- Two apps: `users` (User) and `rides` (Ride, RideEvent). "Modular" is a graded word.
- Read and write serializers are separate. Nested on read, plain ids on write, chosen in
  `get_serializer_class()`.
- Serializers stay thin. Query optimisation lives in the ViewSet's `get_queryset`.
- Filtering and ordering go through django-filter and DRF's `OrderingFilter`.
- Query counts are asserted. If a change raises the count, the test fails — that is the point.

## Do not

- Do not add columns to **Ride**. Indexes yes, columns no.
- Do not add anything to User beyond what authentication requires.
- Do not sort or filter in Python.
- Do not use a serializer field that queries.
- Do not add `django.contrib.gis`.
- **Do not commit `docs/Assessment.pdf`** — publishing their private hiring test on a public repo
  is a bad look. Gitignore it, along with `.venv/` and any `.env`.
- Do not build anything the PDF did not ask for. No dispatch, pricing, or notifications.
- Do not commit code I have not read and understood.

## Working practice

One requirement per commit — the history is explicitly graded and cannot be retrofitted. Every commit
leaves the suite green. Messages say **why**, not what. After each increment, explain what changed
and why before moving on. Compact at commit boundaries.

Progress lives in `PLAN.md`.
