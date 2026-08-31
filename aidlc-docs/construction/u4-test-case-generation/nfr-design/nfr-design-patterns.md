# NFR Design Patterns — U4 Test Case Generation

**Phase**: CONSTRUCTION | **Unit**: U4 | **Stage**: NFR Design
**Version**: 1.0 | **Date**: 2026-08-30

Five patterns specific to U4, on top of the 36 inherited from U1, U7, U2 and U3.

U4 uses more of the inherited set than any unit before it and adds little of its own,
which is the correct shape for a unit whose work is sequencing. Everything U4 does to
a test case, some domain component already knows how to do. What U4 owns is the
**order** those components run in, and what must be true when they do.

---

## 1. Inherited

| Pattern | Use in U4 |
|---|---|
| P-RES-01 Unit of Work | The batch transaction — the strictest use of it in the system |
| P-PRF-01 Bucketed candidate selection | First exercised on generated rather than synthetic data |
| P-SCL-01 Capped pagination | Case and requirement queries |
| P-SEC-01 Two-level validation | Pydantic at the boundary, D7 beneath |
| P-SEC-03 Message sanitisation | Every rejection message, including the personal-data ones |
| P-OBS-01 Correlation propagation | Batch, emission and matrix all carry the run id |
| P-MNT-01 Dependency inversion | S5 depends on ports, never on SQLite |
| P-MNT-02 Import contracts | Enforce that U4 holds no copy of a domain algorithm |
| P-U7-02 Read-only gate evaluation | Stage A, before any case is touched |
| P-U3-02 Informational result field | Planned-vs-generated variance rides a successful result |

**Two of these are being tested for the first time, not merely reused.**

`P-PRF-01` was built in U1 and benchmarked at 10,000 synthetic rows: 8 candidates
selected in 0.29 ms. Synthetic rows distribute evenly across buckets because they were
generated to. Real cases will not — a busy feature will crowd one bucket while others
stay near-empty, and the 50 ms budget of U4-NFR-PRF-02 is written against that skew
rather than against the benchmark.

`P-RES-01` has so far wrapped writes where a partial result would be untidy. Here a
partial result is *wrong*: half a batch leaves the coverage model claiming cases that
have no steps, and the volume report would then reconcile against a corpus that never
existed.

---

## 2. P-U4-01: Deferred Allocation

**Delivers**: U4-NFR-REL-01, -02, -03

Everything that mutates sequence state runs after everything that can reject.

```
for payload in payloads:
    failures += validate(payload)        # B, C, D — collect, never stop
if failures:
    return report_all(failures)          # nothing allocated, nothing written

for case in accepted:
    case.automatability = D6.classify(...)   # E
    case.id             = D5.allocate(...)   # F
uow.cases.upsert_many(accepted)
```

### What the transaction does and does not cover

U1 built the sequence as a **derived** value: `SequenceState.from_existing` rebuilds
the high-water marks from the identifiers already stored, so there is no separate
counter for a rollback to leave stranded. A rejected batch stores nothing, and the
next attempt therefore sees exactly the same starting point.

That covers reissue. It does **not** cover the gaps:

| If allocation ran during construction | Consequence |
|---|---|
| Batch of 5, cases 2 and 4 rejected | Nothing stored — correct |
| Batch of 5, all accepted | TC-1 … TC-5 — correct |
| **Batch of 5, 2 and 4 rejected, remainder stored** | **TC-1, TC-3, TC-5 — two permanent holes** |

The third row is the one deferred allocation prevents. Numbering only the accepted
set, after every rejection is known, is what keeps the corpus gapless — and a hole in
the sequence is a question the operator asks on every review for the life of the
corpus, with no good answer.

*Written during design as an argument about unwinding a persistent counter; corrected
during implementation, where `from_existing` turned out to make that half of the
concern moot. The pattern stands on the gapless-numbering argument alone.*

### Why failures collect rather than stop

Stages B, C and D gather every fault before returning. A batch of 200 cases with four
faults reports four, not the first one four times over.

**The agent is the caller, and the agent regenerates the whole batch.** Stopping at
the first fault would mean four full regeneration cycles to discover four problems,
each one costing a model round-trip against a corporate Copilot quota. Stage A is the
exception because a closed gate makes every case in the batch moot — there is nothing
to collect.

---

## 3. P-U4-02: Ordered Bulk Insert

**Delivers**: U4-NFR-PRF-01

One transaction, five `executemany` calls, ordered so foreign keys resolve.

```
uow.execute_many("INSERT INTO test_case ...",   case_rows)
uow.execute_many("INSERT INTO test_step ...",   step_rows)      # FK -> test_case
uow.execute_many("INSERT INTO test_data ...",   data_rows)      # FK -> test_step
uow.execute_many("INSERT INTO trace_link ...",  link_rows)      # FK -> test_case
uow.execute_many("INSERT INTO integrity_check ...", sentinel)   # last, always
```

A 200-case batch is roughly 1,600 rows. Per-row `execute` pays Python call overhead
1,600 times and re-prepares the statement each time; `executemany` prepares once and
binds in a loop inside SQLite.

### The ordering is a constraint, not a preference

`foreign_keys = ON` is set by U1's L1 `ConnectionFactory` and is not deferred, so a
step inserted before its case fails immediately. The order above is therefore load-
bearing: it is the topological order of the four foreign keys, and changing it breaks
the insert rather than merely slowing it.

**This is the second time L1's foreign-key enforcement has caught a real defect
early** — the first was U2's `resource_id = 0`, where the read-back assertion exposed
an orphaned artefact that would otherwise have been written silently.

### The sentinel goes last

The integrity row asserts that the batch is complete and consistent. Written first, it
would assert a state that does not yet exist; if the insert then failed, the assertion
and the rollback would race to describe the same batch.

### Chunked commits were rejected

Committing every 50 cases would recover from failure faster and would abandon
U4-NFR-REL-01. A partial batch that reports success is worse than a slow one that
reports failure, because the corpus then contains cases nobody reviewed and the volume
report reconciles cleanly against them.

---

## 4. P-U4-03: Value Screening in the Domain

**Delivers**: U4-NFR-SEC-01, -02

The personal-data check is a pure domain function, called from D7's validation stage B
alongside "has at least one step" and "data-dependent steps carry an equivalence
class".

```
# domain/privacy.py — no I/O, no database, no configuration lookup
def screen_value(field: str, value: str) -> PrivacyFinding | None
```

### Why the domain and not the boundary

Rejecting at the MCP boundary, as a Pydantic validator, would catch the value earlier.
It would also put a policy decision inside a schema.

| | Boundary (Pydantic) | Domain (chosen) |
|---|---|---|
| Rejects before construction | Yes | No — the case is built, then refused |
| Property-testable without a database | Yes | Yes |
| Pattern set changes without touching the wire contract | **No** | Yes |
| Sits beside the other nine case rules | No | **Yes** |

The pattern set **will** change. The first month of real Jira stories will produce
false positives nobody predicted, and each fix is a change to what counts as personal
data — a domain rule. Keeping it in the schema would mean the MCP contract shifting
every time the team learns something about its own backlog.

The cost is that a rejected case has already been constructed. That cost is one
discarded object, because P-U4-01 guarantees nothing was allocated for it.

### What is screened, and what is permitted

| Pattern | Permitted synthetic form |
|---|---|
| Email address | RFC 2606 reserved domains — `example.com`, `example.org`, `.test`, `.invalid` |
| Phone number | `555-01xx` reserved range |
| National insurance / social security | Reserved and never-issued prefixes |
| Card number | Published test card numbers only |

The card check applies a **Luhn validation before rejecting**. A 16-digit order
reference is not a card number, and a screen that cannot tell the difference would
reject legitimate test data often enough that someone would turn it off.

**The allow-list is what makes rejection workable.** A rule that refuses personal data
without saying what is acceptable instead is a rule that produces retries rather than
corrections. The rejection message names the field, the pattern matched, and the
permitted form — three facts, and the agent's next attempt succeeds.

---

## 5. P-U4-04: Three-Outcome Emission

**Delivers**: U4-NFR-REL-04, U4-NFR-PRF-06, U4-NFR-MNT-01

Every emitted view lands in exactly one of three states, and the manifest reports all
three.

| Outcome | Condition | Action |
|---|---|---|
| `written` | New, or content changed | File written, hash recorded |
| `unchanged` | Recorded hash equals new content hash | Nothing done |
| `hand_edited` | File on disk differs from its recorded hash | **Skipped**, reported |

### Why `unchanged` is not folded into `written`

A re-emission that writes nothing is exactly correct and indistinguishable from a
broken one unless the report says so. This is the same reasoning that separated
skipped-unchanged from succeeded in U2's ingestion report, and it is the reason
U4-NFR-PRF-06 is measurable at all: "only the features a batch touched were
re-emitted" is a claim about which files moved, and it can only be checked if the
report distinguishes moved from considered.

### Why a hand-edit is skipped rather than merged or overwritten

Three options, and two of them lose work:

- **Overwrite** — the operator's edit is destroyed, silently, by a batch they ran for
  an unrelated feature.
- **Merge** — requires knowing which side is authoritative per hunk. The system does
  not know, and guessing produces a file that is neither what the generator meant nor
  what the operator wrote.
- **Skip and report** — the edit survives; the operator is told the view is now stale
  and decides.

Only the third respects the fact that the corpus, not the view, is the system of
record. The view is derived; the edit is not, and destroying it would teach the
operator never to touch a generated file — which also means never correcting one.

**The detection is three-way, and needs to be.** Comparing the file to the newly
rendered content would flag every genuine change as a hand-edit. The recorded hash is
the third point that separates "the operator changed this" from "the corpus changed".

---

## 6. P-U4-05: Iterator-Returning Query Port

**Delivers**: U4-NFR-SCL-04, -05, U4-NFR-PRF-05

A new `stream_links()` on `TraceRepository`, and the case queries feeding matrix
construction, return iterators that D3's `build_matrix` consumes lazily.

```
def stream_links(self) -> Iterator[TraceLink]   # cursor-backed, not a list
```

**Added alongside `all_links()` rather than replacing it.** `all_links()` has two
existing callers in `tools_read.py` where the result is filtered and capped in memory
anyway, and changing a port signature to serve one new caller would rewrite working
code for no gain. The matrix moves to `stream_links()`; `trace_query` keeps the list.

At 6,000 cases the matrix draws on roughly 9,000 links. Materialising them is perhaps
20 MB — survivable, and it makes memory a function of corpus size, which is the
property U4-NFR-SCL-05 exists to prevent. The matrix is the largest read in the
system and it is the one an operator runs at the end of a baseline, when the corpus is
at its biggest.

**This is a deliberate exception to P-SCL-01's 200-record cap.** A capped matrix is
not a matrix — it is a sample, and a coverage report built from a sample would
understate coverage without saying so. The cap protects interactive queries from
returning unbounded results to the model's context; the matrix is written to a file
and never enters the context, so the reason for the cap does not apply and the
streaming guarantee replaces it.

The uncovered-requirement calculation is what forces the design to be careful:
requirements with no links must appear, so the source set cannot be derived from the
links alone. It comes from a separate streamed query over `requirement`, and the
difference is computed against a set of identifiers rather than of records.

---

## 7. Patterns Considered and Declined

| Pattern | Why not |
|---|---|
| **Parallel case validation** | The batch is capped at 200 and the budget is 10 s. Concurrency would add a failure mode — partially validated batches — to buy time nobody is waiting for |
| **Caching the automatability classification** | D6 is a pure function over signals already in memory. A cache would be slower than the call |
| **A merge strategy for hand-edited views** | See §5. It cannot be done correctly without knowing intent |
| **Pre-computing the traceability matrix** | It would need invalidating on every case, every link and every requirement change — the same objection that ruled out stored coverage summaries in U1 and incremental rebuilds in U3 |
| **A `BatchValidator` component** | The sequence lives in S5 and the checks live in D7. A component holding neither would be a name with nothing behind it |
| **Deferring foreign keys for the batch insert** | `PRAGMA defer_foreign_keys` would remove the ordering constraint and remove the check that has now caught two real defects |

**The pre-computed matrix is the one worth dwelling on**, because it is the third time
the same answer has been reached and the reasoning has sharpened each time. In U1 it
was "a cache needs invalidating". In U3 it was "an incremental build makes the hash
depend on build order". Here it is narrower and harder: the matrix's most valuable
output is the **uncovered** list, and a stale cache reports a requirement as covered
after the case covering it was retired. The failure mode of a stale coverage report is
silent false confidence, which is the exact thing the system was commissioned to
remove.

---

## 8. Pattern-to-Requirement Coverage

| Requirement group | Delivered by |
|---|---|
| U4-NFR-PRF-01 | **P-U4-02** |
| U4-NFR-PRF-02 | P-PRF-01, composite bucket index from U1 |
| U4-NFR-PRF-03, -04, -06 | **P-U4-04** |
| U4-NFR-PRF-05 | **P-U4-05** |
| U4-NFR-SCL-01, -02 | P-PRF-01, P-SCL-01, benchmark headroom |
| U4-NFR-SCL-03 | Stage A cap, BR-U4-3.1 |
| U4-NFR-SCL-04, -05 | **P-U4-05** |
| U4-NFR-REL-01, -02, -03 | **P-U4-01**, P-RES-01 |
| U4-NFR-REL-04 | **P-U4-04** |
| U4-NFR-REL-05, -06 | Stable-identifier resolution, BR-6.2 |
| U4-NFR-REL-07 | L2 migration runner, `verify_reversibility` |
| U4-NFR-SEC-01, -02 | **P-U4-03**, L9 |
| U4-NFR-SEC-03 | L10 rendering rules |
| U4-NFR-SEC-04 | No `eval`/`exec`; asserted by source inspection |
| U4-NFR-SEC-05 | L10 path construction, `.gitignore` |
| U4-NFR-MNT-01, -02 | **P-U4-04**, L10 |
| U4-NFR-MNT-03 | **P-MNT-02** import contracts |

**All 25 U4 NFR requirements have a delivering pattern or component.**
