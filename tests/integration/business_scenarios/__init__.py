"""Business-scenario integration tests.

These are not unit tests with mocks. Each one drives the real HTTP surface the
way a user does - logging in through POST /auth/login, submitting forms, POSTing
JSON to the API - and then asserts on the business outcome: the document numbers
that were issued, the stock that moved, the money the customer owes, and the
journal entries that resulted.

A scenario passes only when the accounting is right. A 200 response with no
journal entry, or with an entry on the wrong account, is a failure, because that
is exactly the class of defect these exist to catch.

Waves, in dependency order:

    wave0  tenant, branch, user       - everything below depends on these
    wave1  cash sale, multi-tender    - the revenue path through three surfaces
    wave2  receipts, cheques, returns - settlement and reversal
    wave3  online warehouse and store - storefront publication and fulfilment
    wave4  purchasing and inventory   - the cost side and stock movements
    wave5  budgets and quotations      - controls that gate the above
    wave6  journal and period close   - the accounting spine itself

Defects found and fixed while writing these are recorded in the commit that
introduced each scenario rather than in a separate findings document, so the
evidence stays next to the test that reproduces it.
"""

from __future__ import annotations
