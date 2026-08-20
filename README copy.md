# Wingz Ride API

A RESTful API built with Django REST Framework that manages ride information —
rides, the users who ride and drive them, and the events recorded against each ride.

Built against the Wingz Python/Django developer assessment. The table definitions,
primary key names and foreign key names come from that brief and are reproduced exactly.

**Contents** — [Setup](#setup) · [Endpoints](#endpoints) · [The query budget](#the-query-budget) ·
[Design decisions](#design-decisions) · [Challenges](#challenges) ·
[Bonus — the SQL report](#bonus--the-sql-report) ·
[Requirement traceability](#requirement-traceability) · [Tests](#tests)

Short version: every requirement is traced to code and a test in the
[traceability table](#requirement-traceability). The two most interesting parts are
[the query budget](#the-query-budget) — 51 queries down to 3, held constant as data grows —
and [why the report collapses events before joining](#-why-the-events-are-collapsed-before-joining).

---

## Setup

Everything runs from a Docker-hosted PostgreSQL and a local virtualenv. No system
libraries are required.

**1. Clone and create the virtualenv**

```bash
git clone https://github.com/abdupa/wingz-ride-api.git
cd wingz-ride-api
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

**2. Create your `.env`**

```bash
cp .env.example .env
```

Then put a real secret key in it:

```bash
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(64))"
```

> **Use that command rather than Django's `get_random_secret_key()`.** Docker Compose
> reads the same `.env` file Django does, and treats `$name` as a variable to
> substitute. Django's generator can emit `$`, which makes Compose warn about
> undefined variables. `token_urlsafe` only produces letters, digits, `-` and `_`.

**3. Start PostgreSQL**

```bash
docker compose up -d
```

Postgres 16, on `localhost:5432`, with a healthcheck. The database name, user and
password are `wingz` — matching the `DATABASE_URL` in `.env.example`.

**4. Migrate and create an admin**

```bash
python manage.py migrate
python manage.py createsuperuser
```

`createsuperuser` prompts for email, first name, last name and phone number, and
creates the account with `role='admin'`. There is no `is_superuser` field — see
*Design decisions* below.

**5. Seed some data (optional but recommended)**

```bash
python manage.py seed --clear
```

Creates an admin, three drivers, eight riders and around 300 rides with four months of
pickup and dropoff events. It is deterministic — the same `--seed` produces the same
database every time, so a number quoted here can be reproduced rather than described.

It also plants three shapes that uniform random data would never produce, each one the
thing a specific requirement needs to be provable: a ride with events either side of the
24-hour boundary, five rides sharing one `pickup_time`, and **one ride with two pickup
events** — without which the bonus report's inflation bug is invisible.

Log in as `admin@wingz.test` / `wingz-admin-password`.

**6. Run**

```bash
python manage.py runserver
pytest
```

The API is at `http://127.0.0.1:8000/api/`.

**7. Get a token**

Every endpoint requires an authenticated user with `role='admin'`.

```bash
curl -X POST http://127.0.0.1:8000/api/auth/token/ \
     -H "Content-Type: application/json" \
     -d '{"email": "you@example.com", "password": "your-password"}'
# {"token":"9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b"}
```

Then send it on every request:

```bash
curl http://127.0.0.1:8000/api/rides/ -H "Authorization: Token 9944b09..."
```

---

## Endpoints

| Resource | URL |
|---|---|
| Users | `/api/users/` · `/api/users/{id_user}/` |
| Rides | `/api/rides/` · `/api/rides/{id_ride}/` |
| Ride events | `/api/ride-events/` · `/api/ride-events/{id_ride_event}/` |

Plus `POST /api/auth/token/` to log in.

All three resources support the full set: `GET` list, `POST` create, `GET` retrieve,
`PUT`/`PATCH` update, `DELETE`.

### Ride list query parameters

| Parameter | Effect |
|---|---|
| `page`, `page_size` | Paginate. Default 20 per page, hard ceiling 100. |
| `status` | Filter by ride status. An unknown value returns `400`, not an empty list. |
| `rider_email` | Filter by the rider's email. Case-insensitive. |
| `ordering` | `pickup_time`, `-pickup_time`, `distance`, `-distance`. An unrecognised field returns `400`. |
| `lat`, `lng` | Reference point for distance. Declared as filters, so they appear in the browsable API's filter form. Required when ordering by distance; adds `distance_km` to each ride. |

```bash
curl "http://127.0.0.1:8000/api/rides/?status=en-route&rider_email=rita@example.com&page_size=50" \
     -H "Authorization: Token 9944b09..."
```

### Error responses

| Situation | Response |
|---|---|
| No credentials | `401` with a `WWW-Authenticate: Token` header |
| Invalid or expired token | `401` |
| Valid token, role is not `admin` | `403` |
| Object does not exist, or page past the end | `404` |
| Method not allowed on that route | `405` |
| Body is not JSON | `415` |
| Malformed JSON, unknown `status`, unknown `ordering` field, bad `page_size`, impossible coordinates, missing `lat`/`lng` when ordering by distance, reference to a user or ride that does not exist, duplicate email | `400`, naming the field |
| Deleting a user who still has rides | `409` |

Rides read and write in different shapes. A `GET` nests the rider and driver in full;
a `POST` or `PATCH` takes their ids:

```jsonc
// GET /api/rides/1/
{
  "id_ride": 1,
  "status": "en-route",
  "id_rider":  { "id_user": 3, "role": "rider",  "first_name": "Rita",  ... },
  "id_driver": { "id_user": 4, "role": "driver", "first_name": "Chris", ... },
  "pickup_latitude": 14.5995,
  ...
}

// POST /api/rides/
{ "status": "en-route", "id_rider": 3, "id_driver": 4, "pickup_latitude": 14.5995, ... }
```

---

## The query budget

Requirement 4 asks for the ride list, with its rider, driver and ride events, in two
queries — three counting the paginator's `COUNT`. That is the only requirement in the
brief with a number attached, so it is the only one that can be measured rather than
judged.

**Three queries, whether the page holds 5 rides or 50:**

```sql
[1] SELECT COUNT(*) FROM "ride"                                  -- the paginator
[2] SELECT ride.*, rider.*, driver.* FROM "ride"                 -- select_related
      INNER JOIN "user" ... INNER JOIN "user" ...                -- two aliased joins
[3] SELECT ... FROM "ride_event"                                 -- Prefetch(to_attr=...)
      WHERE id_ride IN (...) AND created_at >= ...
```

Before the optimisation this list cost `2N + 1` — **51 queries for 25 rides**, two per row
to fetch each rider and driver.

### How it is held there

```python
Prefetch(
    "events",
    queryset=RideEvent.objects.filter(created_at__gte=cutoff).order_by("-created_at"),
    to_attr="todays_ride_events",
)
```

`to_attr` is the part that matters. It puts a plain Python list on each `Ride`, so the
serializer reads an attribute and has no queryset it could accidentally re-filter.

Two ways to get this wrong, both of which return **identical JSON**:

- A `SerializerMethodField` calling `.filter()` — one query per ride.
- `Prefetch` *without* `to_attr`, then `.filter()` in the serializer — calling `.filter()`
  on a prefetched relation discards the cache and re-queries, so you pay for the prefetch
  *and* the N+1.

No correctness test would catch either. The query-count test is the only thing that does,
and it runs at **two data sizes ten times apart** — three queries at 5 rides and at 50.
One data point is an observation; two is evidence the cost is constant.

The cutoff is computed per request. As a module constant it would freeze at server start
and the window would drift silently — correct on deploy day, hours stale a week later,
never an error.

### One honest note on the count

The test uses `force_authenticate`, so it measures exactly what the brief measures:
fetching the ride list with its relations. **A real request over the wire costs four** —
token authentication looks the token up in the database. That query is not part of the
brief's budget and is not engineered away; JWT would remove it by being stateless, at the
cost of a dependency this project does not need.

### The COUNT is the expensive one

On a genuinely very large table, queries 2 and 3 touch only the twenty rows on the page.
The `COUNT` touches every row — PostgreSQL keeps no cached row count. It is the slowest
of the three. Removing it means cursor pagination, which requirement 3's caller-chosen
ordering rules out.

Worth knowing the floor, too: a `json_agg` subquery could inline the events and do the
whole thing in **one** query. That was rejected — raw SQL embedded in a queryset, harder
to read and change, for a target the brief already sets at two.

---

## Design decisions

### The User table has no password, but the brief demands authentication

The specified User table is `id_user`, `role`, `first_name`, `last_name`, `email`,
`phone_number` — nothing to authenticate with. Requirement 2 restricts every endpoint
to users with `role='admin'`, which is impossible without a credential.

Two ways out were considered:

- **Tokens only, no password.** Keeps User byte-identical to the brief; credentials are
  minted out-of-band like API keys.
- **`AbstractBaseUser`**, which adds `password` and `last_login`.

The second was chosen. The brief also asks for a README any developer can follow, and
"log in with your email and password" is a far easier instruction than "run this command
to mint yourself a credential". **These two columns are the only deliberate departure
from the specified tables.**

### No `PermissionsMixin`, and no Django admin

`PermissionsMixin` would add `is_staff`, `is_superuser`, and two join tables for groups
and permissions. None of it is used — the only authorisation rule in this API is
`role == 'admin'`. Leaving it out keeps the user table at eight columns.

That in turn rules out `django.contrib.admin`, which requires exactly those fields. It
is not installed, and there is no `/admin/` route. This is a JSON API; nothing is lost.

For honesty: `django.contrib.auth` still creates `auth_group`, `auth_permission` and
`auth_group_permissions`. Those come from the app itself and cannot be dropped without
losing password hashing. They are unused. The *user* table carries no extra columns and
no join tables.

### Foreign keys set `db_column` explicitly

Django appends `_id` to foreign key columns by default, so `id_rider` would become
`id_rider_id` in the database — silently, with no error. Every foreign key therefore
sets `db_column`, and a test reads `information_schema` to confirm what PostgreSQL
actually built rather than trusting the models.

### `AutoField`, not `BigAutoField`

The brief's tables say INT. Django's default for new projects is `BigAutoField`. Primary
keys are pinned to `AutoField` in settings *and* in both `AppConfig`s, because an
app-level setting silently overrides the project-level one.

Worth noting the tension: requirement 4 says the RideEvent table is expected to grow
very large, and INT caps around 2.1 billion. `BigAutoField` would be the production
choice there. The brief was followed.

### `created_at` uses `default=timezone.now`, not `auto_now_add`

`auto_now_add` makes a field non-editable and always "now". That would make the bonus
SQL report impossible to seed with historical data, the 24-hour window impossible to
test at its boundary, and the RideEvent create endpoint unable to accept a timestamp.

### `Meta.ordering` is correctness, not style

PostgreSQL guarantees nothing about row order without an `ORDER BY`. An unordered
queryset with `LIMIT`/`OFFSET` can return the same row on two pages and skip another
entirely — silently, with plausible-looking output. Every model declares a default
ordering, and every sort ends in a unique column.

### `PROTECT` for rider and driver, `CASCADE` for events

Deleting a user must not silently erase ride history, so those foreign keys are
`PROTECT`. A ride event has no meaning without its ride, so that one cascades.

### Coordinate bounds are constrained; `rider != driver` is not

Latitude within ±90 and longitude within ±180 are physically true, so a check constraint
can never reject data the brief permits. They are enforced in the database and validated
in the serializer, so a bad value returns a readable 400 rather than an IntegrityError
surfacing as a 500.

A constraint that a ride's rider and driver differ was considered and **declined**. It is
obviously sensible, but the brief never states it — and rejecting input the brief allows
would read as a bug rather than rigour.

### Two serializers for Ride

Requirement 3 wants rider and driver nested on read. Nested serializers are read-only in
DRF, and a caller creating a ride should send `id_rider: 7` rather than a whole user
object. One serializer cannot do both cleanly, so `get_serializer_class()` picks by
action.

### Token authentication, not JWT

DRF's built-in `TokenAuthentication` needs no extra dependency, works in a one-line
`curl`, and reduces the README to a single command. JWT is the better answer at scale —
stateless, no database lookup per request, refresh semantics — and would be the choice
for a real deployment. It buys nothing on an assessment and costs a dependency.

Session authentication is enabled alongside it so DRF's browsable API is usable in a
browser.

**The order in settings matters.** DRF decides between `401` and `403` for an
unauthenticated request based on the *first* authentication class. Token auth sends a
`WWW-Authenticate` header and produces `401`; session auth sends none and produces
`403`. Listing session first would make every anonymous request return the wrong status
code. A test pins the ordering.

### A hand-written permission, not DRF's `IsAdminUser`

DRF ships a permission called `IsAdminUser`. It checks `user.is_staff` — a Django
admin-site concept, and a field this project's User model does not have. The names are
close enough to be dangerous; reaching for it would have silently locked everybody out.

`IsAdminRole` checks what the brief actually asks for: the user is authenticated and
`role == 'admin'`.

### Closed by default, with one deliberate hole

The permission is set in `DEFAULT_PERMISSION_CLASSES`, so every endpoint is protected
without anyone having to remember to protect it. A ViewSet added next year is closed
the moment it is registered.

That makes the login endpoint a problem: it is an endpoint too, so you would need an
admin token in order to obtain an admin token. `/api/auth/token/` opts out explicitly.

It authenticates any valid user, not only admins — proving who you are and being allowed
in are separate questions. A rider receives a perfectly valid token that opens no doors,
and a test asserts exactly that.

### Errors were found by walking the API, not by guessing

Error handling is one of the four evaluation criteria, so seventeen edge cases were
probed and their actual status codes recorded. Sixteen already behaved. One did not:

**Deleting a user who still has rides returned `500`.** The rider foreign key is
`PROTECT`, deliberately, so ride history survives a user being removed — and Django
raises `ProtectedError`, which DRF does not recognise, so it fell through as an unhandled
server error. A custom exception handler turns it into `409 Conflict`: the request is
perfectly well formed, it just conflicts with the current state of the data.

`?page_size=abc` was also changed. DRF discards an unparseable value and quietly serves
the default with a `200`, so the caller never learns their parameter was thrown away —
the same failure mode as an ordering typo. It is now a `400`.

A parametrised test asserts that none of ten edge-case URLs returns a `5xx`, so the
absence of server errors is checked rather than assumed.

### Distance sorting runs in the database

```bash
curl "http://127.0.0.1:8000/api/rides/?ordering=distance&lat=14.5826&lng=120.9787"
```

The great-circle distance is computed in SQL as part of the SELECT, and the ordering and
`LIMIT` are applied by PostgreSQL:

```sql
SELECT ride.*, (12742.0176 * ATAN2(SQRT(POWER(SIN(...)), ...))) AS distance
FROM "ride" ...
ORDER BY 10 ASC, "ride"."id_ride" ASC
LIMIT 20
```

Sorting a page in Python after fetching it would sort twenty rows out of however many
exist — page one would hold the twenty *lowest ids*, ordered among themselves, rather
than the twenty *nearest rides*. That is not a wrong order; it is a wrong answer. A test
creates 44 distant rides and then one nearby, and asserts the nearby one is first on
page one — which can only happen if the database did the sorting.

**Haversine, not the spherical law of cosines.** The law of cosines is shorter, but it
takes `acos()` of a value approaching 1 for nearby points, exactly where floating-point
precision collapses — two rides a few metres apart can come out as zero or as noise.
Haversine stays stable at small distances, which is the case that matters when the whole
point is proximity.

The tests check the database's answer against an independent haversine written in Python,
so a mistake in the ORM expression cannot be validated by the same mistake in the
assertion.

### Honest limits of the distance sort

Requirement 3 asks for both sorts to be "as efficiently as possible, assuming the Ride
table is very large". Those two sorts are not equally servable:

- `pickup_time` has a B-tree index. Sorting by it is an index scan.
- **Distance cannot use an ordinary index.** It is computed from two separate columns, so
  there is nothing to index. Every distance sort reads the whole table and sorts it.

The production answer is to store a geography column and put a spatial index on it — and
the brief explicitly forbids changing the Ride table, which is what rules it out. The
next best thing, which the brief does allow, is a PostGIS **expression index**: a GiST
index over `ST_MakePoint(pickup_longitude, pickup_latitude)`, giving index-accelerated
nearest-neighbour ordering without adding a column. That is measured separately rather
than assumed — an expression index has to match the query expression exactly, and a
subtle mismatch is silently ignored while looking like it works.

An annotation costs no extra query. Sorting by distance is still three queries, and a
test holds it there.

### Page-number pagination, not cursor

Cursor pagination is the better answer for deep paging on a very large table: it never
runs a `COUNT`, and it does not degrade at high offsets the way `OFFSET 1000000` does.

It cannot be used here. Cursor pagination requires a fixed, unique ordering key, and
requirement 3 explicitly lets the caller choose the ordering — including a *computed*
distance that exists only for the duration of one query. So offset paging is the right
call precisely **because** of the sorting requirement, not in spite of it.

A `page_size` parameter is accepted with a ceiling of 100, so no caller can ask for the
whole table in one request.

### Case-insensitive email matching happens at write time

The obvious way to filter by rider email is `iexact`. On PostgreSQL that compiles to
`UPPER(email) = UPPER(...)`, which **cannot use the index on email** — so a filter meant
to be polite about capitalisation buys a full scan of the user table.

Emails are lowercased when saved instead. The stored value is canonical, the filter
matches exactly, and the index does its job. Case-insensitivity costs nothing because it
happens once on write rather than on every read.

That correctness depends on the stored value *actually* being canonical — so it is
enforced by a database check constraint (`email = LOWER(email)`), not by `save()` alone.
`save()` is only one way a row gets written; `bulk_create`, `queryset.update()` and raw
SQL all bypass it. See *Challenges* below.

### Every ordering ends in the primary key

PostgreSQL makes no promise about the relative order of rows that tie on the sort
column, and it may answer differently for each query. Each page of a paginated list *is*
a separate query. So when rows tie — fifty rides scheduled for the same pickup time — a
ride can appear on page 1 *and* page 2 while another is never returned at all.

The count still reads correctly. Nothing errors. You would only find it by comparing
pages by hand.

`StrictOrderingFilter` appends the primary key to every ordering, making the order total
and reproducible. A test pages through 45 rides that share one `pickup_time` and asserts
all 45 come back exactly once.

### An unknown ordering field is a 400, not a shrug

DRF's `OrderingFilter` silently discards ordering terms it does not recognise. So
`?ordering=pickup_tim` returns `200` with unsorted data — the typo is invisible behind a
response that looks perfectly fine.

The subclass raises instead, naming the rejected field and listing what is available.

### PostgreSQL

The brief names no database. PostgreSQL was chosen because requirement 3 says to assume
the Ride table is very large, and because the bonus report needs interval arithmetic and
month formatting. Docker Compose keeps the setup to one command.

---

## Challenges

**Django renamed the foreign key columns.** The models read correctly while the database
had `id_rider_id`. Nothing errored. This is why the schema tests query
`information_schema` instead of asserting against the models.

**`makemigrations` reordered the columns.** It appends relational fields to the end of
`CreateModel` and sorts them alphabetically, so `ride` came out with `id_driver` and
`id_rider` after `pickup_time` instead of at positions 3 and 4. The initial migration was
hand-edited to restore the brief's order, then `makemigrations --check` confirmed the
models and migration still agree.

**The user table's column order cannot match the brief.** Django emits inherited fields
first, so `password` and `last_login` sit ahead of `id_user`. There is no way to reorder
them short of reimplementing `AbstractBaseUser`, and column order has no functional
meaning in SQL. It is corrected where it is visible: serializer fields are declared in
the brief's order, and tests hold the JSON key order there.

**`user` is a reserved word in PostgreSQL.** Django quotes identifiers automatically, so
the ORM is unaffected — but any raw SQL must write `"user"` in double quotes.

**Docker Compose and Django share `.env`.** A `$` in a generated secret key made Compose
warn about undefined variables. See the setup note above.

**`bulk_create` silently bypassed the email normalisation.** Lowercasing lived in
`User.save()`, and `save()` is not the only way a row gets written. A user inserted
through `bulk_create` kept whatever case it arrived with — no error, no warning — and
because the `rider_email` filter matches exactly, that rider's rides became unfindable.

Nothing in the project did this yet, but the seed command was about to. It would have
surfaced as "the email filter doesn't work sometimes", which is a miserable thing to
debug. The fix was to move the invariant into a database check constraint so no write
path can dodge it: `bulk_create` with a mixed-case address now fails loudly instead of
succeeding wrongly. Tests cover `create_user`, `bulk_create` and `queryset.update()`.

**Following the README from a clean clone found something the tests did not.** The
project was cloned fresh from GitHub into an empty directory, pointed at a brand-new
database, and every documented step run in order. The whole suite passed and the setup
worked — but reading a real response showed `ride_events_url` returning a relative path
while DRF's paginator returns absolute `next`/`previous` links. A client would have to
resolve the two differently depending on which field it read. No test failed, because
every test asserted the relative form it was given. Using the API caught what testing it
did not.

**Requirement 3 contradicts requirement 4.** Requirement 3 says each ride must include
"its related RideEvents"; requirement 4 says the SQL "must never load the full list of
RideEvents". Both cannot hold. Requirement 4 wins — it is explicit and it is the one
being measured. The ride list carries only the last 24 hours, and a ride's full event
history stays reachable through `/api/ride-events/`, filtered and paginated.

**The field is named for "today" but defined as 24 hours.** Requirement 4 calls it
`todays_ride_events` and then defines it as "the RideEvents from the last 24 hours".
Those differ — at 9am, one is nine hours and the other reaches into yesterday. The text
was followed and the brief's field name kept.

---

## Bonus — the SQL report

Count of trips whose pickup-to-dropoff duration exceeded one hour, grouped by month and
driver. The query lives in [`rides/reports/trips_over_one_hour.sql`](rides/reports/trips_over_one_hour.sql)
so the SQL printed here is the SQL that runs, and cannot drift from it.

```bash
python manage.py seed --clear
python manage.py trip_report
```

```sql
-- Count of trips whose pickup-to-dropoff duration exceeded one hour,
-- grouped by month and driver.
--
-- The events are collapsed per ride before joining, rather than joining
-- ride_event twice -- once for the pickup and once for the dropoff. That
-- second approach reads more naturally and is wrong: if a ride has two pickup
-- events the join multiplies its rows and the trip is counted twice. Nothing
-- errors; the totals simply come out too high and look entirely plausible.
--
-- "user" is quoted because it is a reserved word in PostgreSQL.

WITH trip AS (
    SELECT
        e.id_ride,
        MIN(e.created_at) FILTER (WHERE e.description = 'Status changed to pickup')
            AS picked_up_at,
        MAX(e.created_at) FILTER (WHERE e.description = 'Status changed to dropoff')
            AS dropped_off_at
    FROM ride_event e
    WHERE e.description IN ('Status changed to pickup', 'Status changed to dropoff')
    GROUP BY e.id_ride
)
SELECT
    to_char(t.picked_up_at, 'YYYY-MM')                    AS "Month",
    d.first_name || ' ' || LEFT(d.last_name, 1)           AS "Driver",
    COUNT(*)                                              AS "Count of Trips > 1 hr"
FROM trip t
JOIN ride   r ON r.id_ride = t.id_ride
JOIN "user" d ON d.id_user = r.id_driver
WHERE t.picked_up_at   IS NOT NULL          -- a trip that never started
  AND t.dropped_off_at IS NOT NULL          -- or is still running
  AND t.dropped_off_at - t.picked_up_at > INTERVAL '1 hour'   -- strictly more
-- Grouped by the driver's id, not by the rendered name: two drivers called
-- Chris Hernandez and Chris Huang both display as "Chris H" and would
-- otherwise be silently merged into one row.
GROUP BY 1, d.id_user
ORDER BY 1, 2;
```

### Output against the seeded data

```
Month    Driver    Count of Trips > 1 hr
-------  --------  ---------------------
2026-04  Chris H   4
2026-04  Howard Y  5
2026-04  Randy W   3
2026-05  Chris H   10
2026-05  Howard Y  17
2026-05  Randy W   9
2026-06  Chris H   9
2026-06  Howard Y  11
2026-06  Randy W   7
2026-07  Chris H   13
2026-07  Howard Y  12
2026-07  Randy W   11
2026-08  Chris H   11
2026-08  Howard Y  5
2026-08  Randy W   12
```

### It reproduces the brief's own sample report

The strongest check is not against numbers I chose. `test_it_reproduces_the_briefs_sample_report`
builds exactly the dataset the assessment's sample describes — the same three drivers, the
same four months, the same counts — and asserts the query returns that table verbatim,
in the same order:

```
Month    Driver    Count of Trips > 1 hr        Month    Driver    Count of Trips > 1 hr
-------  --------  ---------------------        -------  --------  ---------------------
2024-01  Chris H   4                            2024-01  Chris H   4
2024-01  Howard Y  5                            2024-01  Howard Y  5
2024-01  Randy W   2                            2024-01  Randy W   2
2024-02  Chris H   7                            2024-02  Chris H   7
2024-02  Howard Y  5                            2024-02  Howard Y  5
2024-03  Chris H   2                            2024-03  Chris H   2
2024-03  Howard Y  2                            2024-03  Howard Y  2
2024-03  Randy W   11                           2024-03  Randy W   11
2024-04  Howard Y  7                            2024-04  Howard Y  7
2024-04  Randy W   3                            2024-04  Randy W   3
   the brief's sample                                  what the query returns
```

**The blanks are load-bearing.** The sample shows no Randy W in February and no Chris H in
April, so the test gives those drivers trips in those months — short ones, 45 and 59
minutes. It also gives Howard Y three trips of exactly 60 minutes in February. If the
query counted all trips rather than only those over an hour, or if "more than" were read
as "at least", extra rows and inflated counts would appear and the comparison would fail.

Matching the counts proves the query counts correctly. Matching the *gaps* proves it
excludes correctly.

### 🔴 Why the events are collapsed before joining

The natural way to write this is to join `ride_event` twice — once for the pickup, once
for the dropoff:

```sql
JOIN ride_event p  ON p.id_ride = r.id_ride AND p.description = 'Status changed to pickup'
JOIN ride_event dr ON dr.id_ride = r.id_ride AND dr.description = 'Status changed to dropoff'
```

**That is wrong, and it fails quietly.** If a ride has two pickup events — a retry, a
correction, a bad dispatch — the join matches both against the dropoff and counts the trip
twice. Nothing errors. The totals are simply too high, and entirely plausible.

Collapsing the events per ride first with `MIN(...) FILTER (WHERE ...)` gives one row per
ride, so the count is right whatever the event table contains.

A test proves it rather than asserting it. One ride, ninety minutes, with a second pickup
recorded a minute in:

```python
assert naive_report()[0][2] == 2      # the double join — wrong, and plausible
assert run_report()[0][2] == 1        # collapsed first — right
```

The seed command plants exactly that ride on purpose. **Without it the bug is invisible**:
with one pickup per ride, the wrong query and the right one return identical numbers.

### Three other details the sample output specifies

**`Chris H` is a last initial**, not a surname — `first_name || ' ' || LEFT(last_name, 1)`.

**Grouped by `d.id_user`, not by the rendered name.** Chris Hernandez and Chris Huang both
display as "Chris H"; grouping by the string would merge two drivers into one row. A test
creates both and asserts two rows.

**"More than 1 hour" is strict** — `> INTERVAL '1 hour'`. A trip of exactly sixty minutes
does not count, and a test pins both sides of that boundary.

Trips still running are excluded naturally: with no dropoff event the duration is `NULL`
and fails the comparison. The `IS NOT NULL` checks make that visible rather than accidental.

`"user"` is double-quoted throughout — it is a reserved word in PostgreSQL.

---

## Requirement traceability

Every discrete requirement in the brief, where it is implemented, and what proves it.
✅ done and tested · ⚠️ done, with an interpretation or a limit recorded alongside it.

### Objective

| # | Requirement | Status | Where | Proof |
|---|---|---|---|---|
| O1 | RESTful API with DRF, managing ride information | ✅ | `config/urls.py` | 3 resources on a router |

### 1 — Use the Django REST Framework

| # | Requirement | Status | Where | Proof |
|---|---|---|---|---|
| 1.1 | Model: Ride | ✅ | `rides/models.py` | `rides/tests/test_schema.py` |
| 1.2 | Model: User | ✅ | `users/models.py` | `rides/tests/test_schema.py` |
| 1.3 | Model: RideEvent | ✅ | `rides/models.py` | `rides/tests/test_schema.py` |
| 1.4 | Serializer: Ride | ✅ | `rides/serializers.py` | `rides/tests/test_crud.py` |
| 1.5 | Serializer: User | ✅ | `users/serializers.py` | `users/tests/test_crud.py` |
| 1.6 | Serializer: RideEvent | ✅ | `rides/serializers.py` | `rides/tests/test_crud.py` |
| 1.7 | Converts **to** JSON | ✅ | read serializers | field-order tests |
| 1.8 | Converts **from** JSON | ✅ | write serializers | create/update tested on all three |
| 1.9 | ViewSets handle CRUD | ✅ | `*/views.py` | full CRUD tested on all three |

### 2 — Authentication

| # | Requirement | Status | Where | Proof |
|---|---|---|---|---|
| 2.1 | API access is restricted | ✅ | `DEFAULT_PERMISSION_CLASSES` | `users/tests/test_authentication.py` |
| 2.2 | Only `role='admin'` may call the endpoints | ✅ | `users/permissions.py`, `users/views.py` | test walks the router registry |

### 3 — Ride List API

| # | Requirement | Status | Where | Proof |
|---|---|---|---|---|
| 3.1 | Endpoint returns a list of Rides | ✅ | `rides/views.py` | `GET /api/rides/` |
| 3.2 | Each Ride includes its related RideEvents | ⚠️ | `todays_ride_events` + `ride_events_url` | see *The query budget* — requirement 4 forbids loading the full set, so the window is inlined and the history linked |
| 3.3 | Includes the related rider | ✅ | `select_related` | `test_read_nests_rider_and_driver` |
| 3.4 | Includes the related driver | ✅ | `select_related` | `test_read_nests_rider_and_driver` |
| 3.5 | Pagination | ✅ | `config/pagination.py` | `rides/tests/test_pagination_and_filtering.py` |
| 3.6 | Filter by ride status | ✅ | `rides/filters.py` | unknown value returns 400 |
| 3.7 | Filter by rider email | ✅ | `rides/filters.py` | index-backed, case-insensitive |
| 3.8 | Sort by `pickup_time` | ✅ | `config/ordering.py` | `rides/tests/test_ordering.py` |
| 3.9 | Sort by distance to a given GPS location | ✅ | `rides/distance.py` | `rides/tests/test_distance.py` — checked against an independent haversine |
| 3.10 | Both sorts on the same endpoint | ✅ | `ordering_fields` | one `?ordering=` parameter serves both |
| 3.11 | Both sorts as efficient as possible on a very large table | ⚠️ | index on `pickup_time`; distance computed in SQL | distance has no usable index — see *Honest limits* |
| 3.12 | Pagination still works when sorting is applied | ✅ | `StrictOrderingFilter` | 45 rides across 3 pages, both sorts, no duplicates |

### 4 — Performance

| # | Requirement | Status | Where | Proof |
|---|---|---|---|---|
| 4.1 | Extra field `todays_ride_events` | ✅ | `RideReadSerializer` | `rides/tests/test_query_budget.py` |
| 4.2 | Only events from the last 24 hours | ✅ | filtered `Prefetch` | 23h in, 25h out, 20h in |
| 4.3 | SQL never loads the full RideEvent list | ✅ | `Prefetch` queryset | `WHERE created_at >= cutoff` |
| 4.4 | Advanced Django features, fewest queries | ✅ | `Prefetch(to_attr=...)` | one query for all rides on the page |
| 4.5 | 2 queries, or 3 counting COUNT | ✅ | `RideViewSet.get_queryset` | **asserts 3 at 5 rides and at 50** |

### 5 — Table definitions

| # | Requirement | Status | Where | Proof |
|---|---|---|---|---|
| 5.1 | Ride: nine fields, exactly | ✅ | `rides/migrations/0001` | read from `information_schema` |
| 5.2 | User: six fields, exactly | ⚠️ | `users/models.py` | exact, plus `password` and `last_login` — required by 2.1, see *Design decisions* |
| 5.3 | Ride_Event: four fields, exactly | ✅ | `rides/migrations/0001` | read from `information_schema` |
| 5.4 | Data types | ✅ | — | `integer`, `varchar(n)`, `double precision`, `timestamptz` |

### Submission

| # | Requirement | Status | Notes |
|---|---|---|---|
| S1 | Hosted in version control | ✅ | public GitHub repository |
| S2 | Clean history, meaningful messages | ✅ | one requirement per commit, bodies explain *why* |
| S3 | README sets up without trouble | ✅ | cloned from GitHub into an empty directory against a new database; every step run in order, the whole suite green |
| S4 | README records design decisions | ✅ | each with the alternative rejected |
| S5 | README records challenges | ✅ | all real, all cost real time |

### Evaluation criteria

| # | Criterion | Status | Notes |
|---|---|---|---|
| E1 | Functionality — every requirement | ✅ | every row above; 130 tests |
| E2 | Code quality — modular, readable, maintainable | ✅ | two apps, thin serializers, optimisation isolated in `get_queryset` |
| E3 | Error handling | ✅ | `config/exceptions.py` · `rides/tests/test_error_handling.py` — 17 edge cases probed, the one 500 fixed, no path returns 5xx |
| E4 | Performance | ✅ | three queries, held constant across data sizes |

### Bonus — SQL

| # | Requirement | Status | Where |
|---|---|---|---|
| B1 | Raw SQL statement | ✅ | `rides/reports/trips_over_one_hour.sql` |
| B2 | Included in this README | ✅ | *Bonus — the SQL report*, above |
| B3 | Counts trips longer than one hour | ✅ | strict `>`; 60 min excluded, 61 min counted |
| B4 | Grouped by month | ✅ | `to_char(picked_up_at, 'YYYY-MM')` |
| B5 | Grouped by driver | ✅ | by `id_user`, so same-initial drivers stay separate |
| B6 | Output matches the sample's shape | ✅ | Month · Driver · Count, `Chris H` style |
| B7 | Derived from the two event descriptions | ✅ | `FILTER (WHERE description = ...)` |

---

## Tests

```bash
pytest
```

Tests assert what the database actually did, not what the code intends to do. Query
counts are asserted, so a change that adds a query fails the suite.
