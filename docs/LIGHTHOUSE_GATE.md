# The Lighthouse gate: what it measures, and why the score used to swing

Scope: the `lighthouse-ci` job in `.github/workflows/ci.yml`, the lhci config
(`scripts/lighthouserc.json`) and the reporter
(`scripts/lint/report_lighthouse_scores.py`).

This note records the diagnosis of a flaky gate, the rule the gate now applies,
and the findings that are still open. Every number below was measured, either
on a developer box against a local PostgreSQL 18 with the same app, or from a
real Lighthouse run. Nothing here is estimated.

---

## 1. The symptom

One CI run reported, for the landing page `/`:

```
FAIL performance  65.0  (gate 90)
```

The same commit, on the next run, reported 97 for the same URL and the same
code. The other audited page (`/auth/login`) scored 97 in the failing run.

A gate whose verdict flips on identical code is not measuring the code. It was
measuring the runner.

## 2. Diagnosis

There are two independent causes. The first is a measurement artefact and is
fixed. The second is a real property of the landing page, is not fixed here,
and is written up as a finding in section 5.

### 2.1 The server was cold, and it was cold differently every time

`gunicorn` was started with its default worker count (`2*CPU+1`). Two things
follow from that, and both were measured:

**Every worker runs the whole `create_app()` path at boot.** That path seeds
the platform data and then verifies it - `run_system_integrity_check`,
`run_default_tenant_maintenance_api` and the seed-manifest probes
(`app/factory.py:100-159`, `app/bootstrap.py:177-278`). Measured on a
developer box, with the CI schema already migrated:

```
boot(create_app)      =    9.637s
```

With the default worker count on a 4-core runner that is nine processes
seeding the same tables at the same time, against one PostgreSQL, and the
`lighthouse-ci` job's readiness poll only waits for **one** of them to answer.
The others can still be seeding while the audit starts.

**The first request a worker serves is several times slower than the next
one.** Same process, same page, measured:

```
/                  run1     454.5ms  -> 200  53KB
/                  run2      33.0ms  -> 200  53KB
/                  run3      28.1ms  -> 200  53KB
/auth/login        run1     128.8ms  -> 200   8KB
/auth/login        run2      18.3ms  -> 200   8KB
```

The first request pays the lazy imports (`routes/public.py:91` imports
`SaaSProvisioningService` inside the view), the Jinja compile of an 820-line
template plus its two includes, and the first database connection of that
process.

The audit landed on a worker chosen at random. When that worker had never
rendered the page, ~420ms of runner overhead was charged to the page's
performance score.

### 2.2 One sample decided the gate

`scripts/lighthouserc.json` had `collect.numberOfRuns: 1`. A single Lighthouse
run decided the whole verdict, so a single cold request decided it.

### 2.3 The landing page has a render-blocking third-party dependency

`templates/public/landing.html:42` loads

```html
<link href="https://fonts.googleapis.com/css2?family=Inter:...&family=Tajawal:...&display=swap" rel="stylesheet">
```

which is on the critical path to the first paint, from a host the CI runner
does not control. The login page does **not** have this problem: it serves
Tajawal from the repository (`templates/auth/login.html:22` ->
`static/fonts/tajawal/tajawal.css`).

Measured locally, same page, same machine, only the font request changed:

| font request | FCP | LCP | performance |
|---|---|---|---|
| reachable (real Google Fonts) | 875-939ms | 1555-1598ms | 89-90 |
| fails fast (connection refused) | 609-612ms | 1150-1153ms | 97 |

The third-party stylesheet is worth ~7-8 performance points and ~250-330ms of
first paint *when it is fast*. When it is slow, it is a render-blocking
request: the browser cannot paint until it resolves, so FCP and LCP - 35% of
the performance score - move with it. A runner whose route to
`fonts.googleapis.com` takes a few seconds produces exactly the kind of score
that was reported.

This is a property of the page, not of the runner: every real visitor to `/`
pays the same third-party round trip. It is section 5's finding.

### 2.4 A run can also fail to produce a score at all

One of six local runs of `/auth/login` produced a Lighthouse report with a
**null** performance score: the `largest-contentful-paint` audit failed with
`NO_LCP`, and Lighthouse leaves the whole category null. The old reporter
treated a missing score as "MISSING" and failed the job on it, and it also
counted such a run as a 0 in the median - which would have made the gate
*stricter* on a measurement that never happened.

---

## 3. What the gate measures now

The rule, printed by the reporter on every run:

> Every audited URL is measured **N = `collect.numberOfRuns` = 3** times. The
> gate is decided on the **median run** of those N - the run whose performance
> score is the median of the runs - and every category of that run has to
> clear its floor. Each category's **median** across the runs has to clear its
> floor too.

Consequences, all of them intended:

* One cold run can no longer flip the gate. With runs of 65 / 94 / 97 the
  median is 94 and the gate passes, while the report prints
  `runs performance 65.0 / 94.0 / 97.0 ... spread 32.0` and an
  "unstable measurement" warning, so the swing is visible instead of hidden.
* A genuinely slow page is still caught: 65 / 65 / 97 has a median of 65 and
  fails, and so does every run of a page that is slow in all three.
* **No floor moved.** Performance 90, accessibility 90, best-practices 90, SEO
  65 are unchanged, and the reporter still reads them from
  `scripts/lighthouserc.json` so there is only one copy.

The server is warmed before the audit, and the audit runs against one worker:

* `gunicorn --worker-class gthread --workers 1 --threads 4` - one worker means
  one boot (one seeding pass, no herd), and it removes the lottery of which
  worker answers the audited request. Threads keep the browser's parallel
  asset fetches parallel, so the page is not penalised for the single
  process. This job measures a page; concurrency is measured by
  `tests/integration/test_sales_concurrency_load.py`.
* The warm-up step fetches each audited URL three times (requiring a settled
  200, refusing a redirect chain) and then fetches every `/static/...` asset
  the page references. It prints the timings, so the log shows the cold
  request and the warm ones next to each other. Locally:

  ```
  http://localhost:5000/ warm#1 -> 200 (0 redirect(s), 0.472999s)
  http://localhost:5000/ warm#2 -> 200 (0 redirect(s), 0.236250s)
  http://localhost:5000/ warm#3 -> 200 (0 redirect(s), 0.242443s)
  ```

  `gunicorn-access.log` is uploaded with the reports, so the server-side
  duration of the audited requests themselves is in the artifact.

`lhci assert` now runs from `.lighthouse-gate/`, where the reporter wrote the
median run of each URL. Pointed at the raw `.lighthouseci/` it would assert
every individual run, and one cold run would fail the build - exactly the
artefact this change exists to stop measuring. The raw runs stay in
`.lighthouseci/` as the evidence, and the numbers `lhci assert` checks are the
numbers the report printed.

## 4. How the reporter decides

`scripts/lint/report_lighthouse_scores.py`:

* reads the floors and the expected number of runs from
  `scripts/lighthouserc.json` (one source of truth);
* groups the reports by URL and identifies a *run* by its `fetchTime`, so the
  two copies lhci writes of every run (one from `collect`, one from the
  filesystem `upload`) collapse into one;
* fails if two copies of the same run disagree - a corrupted copy must not be
  able to approve a regression;
* excludes a run that produced no performance score from the median, and
  prints it by name with Lighthouse's reason (`NO_LCP`);
* prints every run's score, the median, the min, the max and the spread for
  every category, and warns when the spread exceeds 5 points;
* writes the median run of each URL to `.lighthouse-gate/.lighthouseci/` for
  `lhci assert`.

## 5. The finding that is still open

**F1 - the landing page blocks its first paint on a third party.** P0 for the
page, not for the gate. `templates/public/landing.html:42` pulls a
render-blocking stylesheet for 12 font weights of two families from
`fonts.googleapis.com`, and the browser cannot paint before it resolves. The
repository already contains the fix for the login
page: Tajawal is vendored under `static/fonts/tajawal/` and served locally
(`templates/auth/login.html:17-22`). The landing page needs the same
treatment - and `Inter` is not vendored yet, so that is a decision about
which weights to ship, not a one-line change. Until then the landing page's
performance score carries a third-party latency that the CI runner does not
control, and that is the remaining source of run-to-run movement in this
gate. It was deliberately **not** papered over by blocking the domain in the
Lighthouse settings: that would have made the number stable by measuring less.

Two more things were found on the way, and both are handled rather than
open, but they are worth knowing before someone reads them as page defects:

**The boot cost is paid per worker.** 9.6s of seeding and manifest
verification in every process that calls `create_app()`. The gate now runs one
worker, so it does not hit the herd, but a production deployment with N
workers pays it N times, and the worker that boots last serves its first
request into that cost. A `SKIP_SYSTEM_INTEGRITY` boot path for the workers
that are not the first would remove it; that is a product change, not a CI
change.

**A Lighthouse run can produce no performance score.** `NO_LCP` on
`/auth/login`, one run in six locally. The reporter now names the run and
excludes it from the median instead of failing the job on it or counting it
as a zero, but the underlying flake is in Lighthouse's measurement of a page
whose LCP element is small.

## 6. Reproducing this locally

Windows/PowerShell, with the repository's virtualenv and a local PostgreSQL:

```powershell
$env:DATABASE_URL = "postgresql://azad_app:azad_app_pass@localhost:5432/lh_ci_test"
$env:SECRET_KEY   = "test-secret-key"
$env:OWNER_PASSWORD = "TestOwner@1234567890123456!"
$env:APP_ENV      = "testing"
$env:CACHE_TYPE   = "null"        # CI has no Redis either
.venv\Scripts\python.exe -m flask --app app:create_app run --port 5000 --with-threads
```

then, from a second shell, `npm install -g @lhci/cli` and

```powershell
lhci collect --config=scripts/lighthouserc.json
lhci upload  --config=scripts/lighthouserc.json
.venv\Scripts\python.exe scripts/lint/report_lighthouse_scores.py
cd .lighthouse-gate; lhci assert --config=../scripts/lighthouserc.json
```

gunicorn does not run on Windows, so the local rehearsal uses the Flask
development server; the numbers are the same order of magnitude, the
cold-versus-warm difference included.
