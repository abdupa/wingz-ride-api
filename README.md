# Wingz Ride API

A RESTful API built with Django REST Framework that manages ride information —
rides, the users who ride and drive them, and the events recorded against each ride.

Built against the Wingz Python/Django developer assessment. The table definitions,
primary key names and foreign key names come from that brief and are reproduced exactly.

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

**5. Run**

```bash
python manage.py runserver
pytest
```

The API is at `http://127.0.0.1:8000/api/`.

**6. Get a token**

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
| `ordering` | `pickup_time` or `-pickup_time`. An unrecognised field returns `400`. |

```bash
curl "http://127.0.0.1:8000/api/rides/?status=en-route&rider_email=rita@example.com&page_size=50" \
     -H "Authorization: Token 9944b09..."
```

| Situation | Response |
|---|---|
| No credentials | `401` with a `WWW-Authenticate: Token` header |
| Invalid or expired token | `401` |
| Valid token, role is not `admin` | `403` |
| Admin, object does not exist | `404` |

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

## Requirement traceability

| Brief | Where | Proof |
|---|---|---|
| Models for Ride, User, RideEvent | `users/models.py`, `rides/models.py` | `rides/tests/test_schema.py` |
| Serializers, both directions | `users/serializers.py`, `rides/serializers.py` | `*/tests/test_crud.py` |
| ViewSets with CRUD | `users/views.py`, `rides/views.py` | full CRUD tested on all three |
| Table definitions | migrations | column names, order and types read from `information_schema` |
| Admin-role restriction | `users/permissions.py`, `users/authentication.py` | `users/tests/test_authentication.py` — walks the router |
| Pagination, filter by status and rider email | `config/pagination.py`, `rides/filters.py` | `rides/tests/test_pagination_and_filtering.py` |
| Sort by `pickup_time` | `config/ordering.py` | `rides/tests/test_ordering.py` |
| Sort by distance | — | *in progress* |
| `todays_ride_events` in 2 queries + COUNT | — | *in progress* |
| Bonus SQL report | — | *in progress* |

---

## Tests

```bash
pytest
```

Tests assert what the database actually did, not what the code intends to do. Query
counts are asserted, so a change that adds a query fails the suite.
