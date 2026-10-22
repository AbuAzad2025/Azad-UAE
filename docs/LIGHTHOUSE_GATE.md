# The Lighthouse gate: what it measures, and why the score used to swing

Scope: the `lighthouse-ci` job in `.github/workflows/ci.yml`, the lhci config
(`scripts/lighthouserc.json`) and the reporter
(`scripts/lint/report_lighthouse_scores.py`).

This note records the diagnosis of a flaky gate, the rule the gate now applies,
and the findings it produced. Every number below was measured, either on a
developer box against a local PostgreSQL 18 with the same app, or from a real
Lighthouse run. Nothing here is estimated.

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

There were three independent causes. The first is a measurement artefact and is
fixed. The second is a real property of the landing page, and it is fixed now
too - section 5 records what was done and what it bought. The third is a fault
in the job's own shell code, and it is what made the gate report "nothing was
measured" instead of reporting a failure.

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

### 2.3 The landing page had a render-blocking third-party dependency

`templates/public/landing.html:42` loaded

```html
<link href="https://fonts.googleapis.com/css2?family=Inter:...&family=Tajawal:...&display=swap" rel="stylesheet">
```

which was on the critical path to the first paint, from a host the CI runner
does not control. The login page did **not** have this problem: it served
Tajawal from the repository (`templates/auth/login.html:22` ->
`static/fonts/tajawal/tajawal.css`).

Measured locally, same page, same machine, only the font request changed:

| font request | FCP | LCP | performance |
|---|---|---|---|
| reachable (real Google Fonts) | 875-939ms | 1555-1598ms | 89-90 |
| fails fast (connection refused) | 609-612ms | 1150-1153ms | 97 |

The third-party stylesheet was worth ~7-8 performance points and ~250-330ms of
first paint *when it was fast*. When it is slow, it is a render-blocking
request: the browser cannot paint until it resolves, so FCP and LCP - 35% of
the performance score - move with it. A runner whose route to
`fonts.googleapis.com` takes a few seconds produces exactly the kind of score
that was reported.

This was a property of the page, not of the runner: every real visitor to `/`
paid the same third-party round trip. It is section 5's finding, and it is
closed.

### 2.4 A run can also fail to produce a score at all

One of six local runs of `/auth/login` produced a Lighthouse report with a
**null** performance score: the `largest-contentful-paint` audit failed with
`NO_LCP`, and Lighthouse leaves the whole category null. The old reporter
treated a missing score as "MISSING" and failed the job on it, and it also
counted such a run as a 0 in the median - which would have made the gate
*stricter* on a measurement that never happened.

### 2.5 A step that died silently, and reported itself as "nothing was measured"

Run `39674996405`, job `lighthouse-ci`, is the evidence. The job's own log:

```
21:00:58.43   ##[group]Run # One worker, several threads, on purpose.   <- 'Start app server'
21:01:01.72   ##[group]Run # The audit must measure a WARM page ...      <- 'Warm up and verify the audited pages'
21:01:01.76   ##[error]Process completed with exit code 1.
21:01:01.767  ##[group]Run python scripts/lint/report_lighthouse_scores.py
21:01:01.820  FAIL: no usable Lighthouse report in .lighthouseci/ - nothing was measured.
```

The warm-up step ran for **38 milliseconds and printed nothing**: no `warm#`
line, no `::error::` line, no gunicorn log. A step that prints nothing and
ends immediately is not a step that worked.

The step was not skipped - the API records it as **failed**, and the step
before it as **succeeded**. It was killed by its own shell:

```
shell: /usr/bin/bash -e {0}
```

GitHub runs every `run:` block under `bash -e`, and the block began with

```bash
read -r code hops secs < <(curl -sSL -o /dev/null \
  -w '%{http_code} %{num_redirects} %{time_total}' "$url" || echo '000 99 0')
```

`curl`'s `-w` output has **no trailing newline**. `read` therefore reaches EOF
without finding its delimiter and returns **1** - and `bash -e` turns that
into an exit. So the step died on the first request that *succeeded*, before
it had printed a single line. Reproduced locally against a working server,
under the same `bash -e`:

```
$ bash -e old_warmup.sh
$ echo $?
1
```

No output. Exit 1. Exactly the 38ms hole in the log.

Two things made this expensive. The failure was invisible at the point it
happened, and the message an engineer finally read - three steps later - was
`nothing was measured`, which names neither the cause nor the step. And the
step before it had no failure path of its own: `Start app server` polled
`/auth/login` up to 90 times and, if the server never answered 200, simply
fell out of the bottom of the loop and **exited 0**. A server that never came
up was reported as a server that did.

Both are fixed now - section 3 describes what the steps do.

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

### 3.1 The two steps that decide whether anything is measured at all

The audit only means something if the server was up and the pages were real.
Both facts are now **gates**, not assumptions.

**`Start app server` - readiness is a gate.** The loop has to *end* in a 200:

* a redirect is not readiness (no `-L`), so a 302 keeps the loop waiting;
* a connection refusal is not readiness either, and it is reported as `000`;
* a gunicorn that is no longer running ends the loop immediately, instead of
  after 90 silent attempts;
* if the loop ends without a 200, the step **fails** and prints the gunicorn
  error log, so the boot traceback is in the job log:

  ```
  ::error::gunicorn is no longer running - it died during boot (attempt 1, last status 000)
  ::error::The app server never answered 200 on /auth/login (last status: 000).
  ::error::The audit below cannot run against a server that is not up - read gunicorn.log for the boot traceback.
  --- gunicorn.log ---
  (no gunicorn.log - the server never wrote one)
  ```

  The step used to exit 0 in exactly this situation, which is how a server
  that never came up was reported as a server that did.

**`Warm up and verify the audited pages` - it cannot die quietly.** The
`read < <(...)` is gone. Every number now comes out of a command
substitution, every variable is initialised before it is read
(`code=000 hops=0 secs=0`), and the value is parsed out of a here-string,
which always ends with a newline and therefore always returns 0. The step
prints what it did on **every** path - the URLs it warmed, the timings, every
static asset it fetched and its status - and it ends with a summary line. On
the failure paths it prints an `::error::` line naming the URL and the
status, prints the gunicorn log, and exits 1.

It also fails on an asset that is not served. A page that links an asset the
server does not have is a broken page, and lhci would have scored it without
complaining:

```
::error::/static/fonts/tajawal/tajawal-900-latin.woff2 answered 404 - the page links an asset the server does not serve
```

**`Report measured scores` - the message names the step.** When there is no
report, the reporter now says where the measurement was lost, because that is
the message an engineer will read:

```
FAIL: no usable Lighthouse report in .lighthouseci/ - nothing was measured.
      This step only reads what lhci wrote; the measurement was lost EARLIER,
      in this job's own log. Read these steps, in this order:
        1. 'Start app server'                     - did the server ever answer 200?
        2. 'Warm up and verify the audited pages' - did every audited URL settle on 200?
        3. 'Run Lighthouse CI'                    - did `lhci collect` / `lhci upload` run?
      The first one that FAILED is the cause; this step is only where the absence became visible.
```

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

## 5. The findings

### F1 - the landing page blocked its first paint on a third party. CLOSED.

**What it was.** `templates/public/landing.html:42` pulled a render-blocking
stylesheet for 12 font weights of two families from `fonts.googleapis.com`,
and the browser could not paint before it resolved. The repository already
contained the fix for the login page: Tajawal is vendored under
`static/fonts/tajawal/` and served locally.

**What was done.** Every family the project uses is now vendored under
`static/fonts/`, one directory per family, one file per (weight, unicode
subset) - the same shape Google Fonts serves, so the browser fetches only the
subsets a page actually renders:

| family | files | weights | referenced by |
|---|---|---|---|
| Tajawal | 12 woff2 + `tajawal.css` | 300/400/500/700/800/900 (arabic + latin) | `partials/head.html`, `layouts/base_print.html`, `auth/login.html`, `shop/base.html`, the `public/` pages |
| Inter | 5 woff2 + `inter.css` | variable 100-900 (latin, latin-ext, cyrillic, greek, vietnamese) | `partials/head.html`, `public/landing.html`, `public/pricing*.html`, `public/user_guide_en.html` |
| Noto Sans Arabic | 5 woff2 + `noto-sans-arabic.css` | variable 100-900 (arabic, latin, latin-ext, math, symbols) | `partials/head.html` |
| Sora | 2 woff2 + `sora.css` | variable 400-800 (latin, latin-ext) | `shop/base.html` |
| Amiri | 6 woff2 + `amiri.css` | 400/700 (arabic, latin, latin-ext) | `public/donate_azad.html`, `public/donate_thanks.html` |
| Rubik | 3 woff2 + `rubik.css` | variable 300-900 (arabic, latin, latin-ext) | `public/donate_azad.html`, `public/donate_thanks.html` |

The font files are **in the repository**: a font fetched at build time is not
a font, and there is no build step that produces them. Every `@font-face`
`src:` resolves to a file that exists, and every one of the 33 `.woff2` files
is a real woff2 (non-empty, `wOF2` magic).

`scripts/lint/check_font_assets.py` is the gate that keeps it true. It fails
when an `@font-face` `src:` or a template's `url_for('static', filename=
'fonts/...')` does not resolve, when a vendored file is not a real woff2, when
a stylesheet or a template names a third-party font host, and when a font
stack has no generic fallback - so a font that cannot be loaded degrades the
type and never the text. It runs in the `lint-audit` job next to the other
CSS and template gates.

**What it bought.** Measured on the same machine, against the same app and
the same server, back to back - the only difference is where the fonts come
from. Three Lighthouse runs per URL, the gate's own rule (median of three):

| `/` (the landing page) | before (Google Fonts) | after (repository) |
|---|---|---|
| performance | 91.0 (91 / 90 / 91) | **95.0 (94 / 95 / 96)** |
| FCP | 931-972ms | **668-765ms** |
| LCP | 1646-1677ms | **1331-1405ms** |
| Speed Index | 1572-1628ms | **1186-1320ms** |
| third-party font requests | 11 (1 stylesheet + 10 woff2) | **0** |

The gate is decided on the median of three, and the median moved from 91.0 to
95.0 with **no floor moved**. The margin over the performance floor went from
1 point to 5.

The change is not only a score. The 11 third-party requests are gone, so the
page no longer has a dependency whose latency the CI runner does not control
- the remaining source of run-to-run movement in this gate. The design is
unchanged: the same families and the same weights, served locally. The
`unicode-range` of every vendored subset is the range Google Fonts itself
serves for that family, and the coverage of the Tajawal subsets is identical
to the coverage of the file it replaced.

### F2 - the job reported "nothing was measured" instead of reporting a failure. CLOSED.

Described in section 2.5. The readiness check now fails the step with the
gunicorn log, the warm-up step cannot die quietly, and the "nothing was
measured" message names the three steps the engineer has to read. The
rehearsal of all four paths (server up / server down, warm-up success /
warm-up failure) is in section 6.

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
.venv\Scripts\python.exe -m flask --app app.factory:create_app run --port 5000 --with-threads
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

`.lighthouseci/` and `.lighthouse-gate/` are **local output, never source**.
Both are in `.gitignore`; the `lighthouse-ci` job regenerates them on every
run.

### 6.1 Rehearsing the two CI steps

The step bodies can be extracted from the workflow and run under the same
shell the runner uses, which is how the silent failure in section 2.5 was
reproduced and how the fix was verified:

```bash
# the runner's shell
bash -e warm_up.sh
```

All four paths, rehearsed locally against a working server and against a
stopped one:

| path | what it printed | exit |
|---|---|---|
| readiness, server up | `::notice::gunicorn answered 200 on /auth/login after 1 attempt(s)` | 0 |
| readiness, server down | `::error::gunicorn is no longer running ...` + `::error::The app server never answered 200 ...` + the gunicorn log | 1 |
| warm-up, server up | one `warm#N -> 200` line per URL per round, one `asset ... -> 200` line per static asset, and the closing summary | 0 |
| warm-up, server down | `::error::<url> settled on 000, not 200 (round 1 of 3)` + the gunicorn log | 1 |

The old warm-up body, against the same working server, under the same
`bash -e`: **no output at all, exit 1**.
