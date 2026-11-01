# Grant Oversight: Relationship Analysis Engine

How Veritas decides that a contractor or vendor on a grant application is a
related party, and why the answer holds up when an investigator or a grantee's
lawyer asks "how do you know?"

Code: `backend/app/agent/relationships.py` (engine), `backend/app/agent/grants.py`
(`ConflictOfInterestTool`), `frontend/src/components/RelationshipGraph.tsx` (graph view),
`backend/tests/test_relationships.py`.

## Why name matching is not enough

The fraud that matters is designed to defeat name matching. The PI's spouse runs
the "independent" subcontractor under her own name. The vendor is owned by a
holding company that is owned by the PI. Two shell companies share nothing but a
phone number and a suite. Veritas therefore treats names as one weak signal among
many and reasons over identifiers and corporate structure instead.

## Three layers

### 1. Entity resolution on identifiers

Every party (applicant, key personnel, contractors, vendors, and the officers,
owners, spouses and household members pulled in from records) is normalised to
canonical identifiers:

| Identifier | Normalisation |
|---|---|
| Person name | Honorifics and suffixes stripped, `Last, First` reordered, nicknames resolved (`Dan` = `Daniel`), Jaro-Winkler for typos |
| Organisation name | Legal suffixes (`LLC`, `Inc`, `L.L.C.`) and filler words removed |
| Address | Street-suffix abbreviation, ZIP+4 collapsed, unit split out so same-building and same-suite are distinguished |
| Phone / email | Digits only; Gmail dots and `+tags` removed; private email domains kept as a signal, public ones ignored |
| Tax ID / bank account | Digits only; bank identifiers matched on a salted hash, never stored in the clear |

### 2. Probabilistic scoring (Fellegi-Sunter record linkage)

Each matched signal carries a log-likelihood ratio `log2(m / u)`: `m` is how often
the signal matches when two parties really are related, `u` how often it matches
by coincidence. Signals are summed and combined with a prior (2% of applicant and
counterparty pairs are related) to produce a posterior probability.

| Signal | Bits | Notes |
|---|---|---|
| Same tax ID | 16.6 | Same entity or DBA |
| Same bank account | 16.5 | |
| Marriage record | 16.6 | From provider |
| Same phone | 13.1 | |
| Officer / owner overlap | 13.1 | From registry |
| Same residential address | 12.0 | |
| Same commercial address incl. unit | 6.9 | Alone routes to review; confirms with corroboration (see backtest) |
| Same private email domain | 9.5 | |
| Same full name, one side has no identifiers to check | 6.9 | Soft: routes to review, never confirms |
| Shared surname | 4.8 to 6.0 | Weighted by surname frequency: Smith scores lower than Hale |
| Same building, different unit | 2.7 | Multi-tenant; related parties usually share the suite |
| Same full name, disjoint addresses and phones | 3.9 | Probably two people |
| Formed within 90 days of application | 2.3 | Applicant-counterparty pairs only |
| Same registered agent | 2.3 | Nearly meaningless alone |
| Same registered-agent / mail-drop address | 2.6 | Discounted because thousands of companies share it |

Two bands come out of this:

- **Confirmed** (≥ 80% and at least one hard identifier or registry record on every hop): reported as a conflict.
- **Review** (35% to 80%, or soft evidence only): handed to the autonomous resolver with the exact pair and the exact check needed. A shared surname can never, by itself, confirm a conflict. It can only trigger a records pull.

### 3. Graph link analysis

Registry and vital-record edges (`officer_of`, `owner_of` with percentages,
`spouse`, `household`) and inferred edges are combined into one graph. For each
counterparty the engine searches for the best path from the applicant side, up to
three hops, scoring by probability and preferring paths built from records over
paths built from inference. It also computes indirect ownership by multiplying
percentages along ownership chains.

Example output for the demo scenario:

```
Daniel Hale → is married to Jennifer Hale → is an officer of Northstar Analytics LLC
  spouse_controlled_entity, 100%, 2 CFR 200.318(c)(1)

Daniel Hale → owns 60% of Hale Family Holdings LLC → owns 100% of Summit Field Services Inc
  indirect_ownership 60%, 2 CFR 200.318(c)(1)

Daniel Hale → may be related to Front Range Statistical Consulting LLC
  possible_family, 56%, REVIEW: officer Patricia Hale shares a surname; pull vital records

Dell Technologies Inc: not flagged (same registered agent only)
```

## Uniform Guidance mapping

| Finding | Provision |
|---|---|
| Counterparty controlled by or tied to an immediate family member | 2 CFR 200.318(c)(1) |
| Applicant personnel hold a direct or indirect financial interest | 2 CFR 200.318(c)(1) |
| Counterparty is a parent, affiliate or subsidiary under common or operational control | 2 CFR 200.318(c)(2) |
| Shell cluster or shared operations defeating competition | 2 CFR 200.319 |
| Suggestive but unconfirmed relationship | 2 CFR 200.112 disclosure request |

## Data providers

The engine calls a `RelationshipDataProvider` for corporate registry, property
and vital records. `MockRelationshipProvider` ships a deterministic test world so
everything above runs without API keys. Production providers plug in behind the
same three methods (`enrich_organization`, `enrich_person`,
`is_registered_agent_address`): state Secretary of State APIs or OpenCorporates
for officers and owners, county recorder data for property, a commercial
aggregator for household and marriage records, and the agency's own vendor
master for bank account hashes. With no provider at all the engine still links
parties on whatever the application itself contains (addresses, phones, EINs,
disclosed owners).

## Identity resolution rules

Most false accusations in relationship analysis come from merging two people
who share a name. The engine therefore:

- resolves nicknames and initials but treats an initial-only match ("S. Ibarra" vs "Samuel Ibarra") as soft evidence;
- keeps same-named people as separate nodes when their addresses, phones and emails are disjoint;
- refuses to merge an applicant-side person who has no identifiers with a same-named record found through a counterparty's household or officer list;
- passes the listing company's address to the provider as a disambiguation hint, and expects the provider to return nothing rather than guess when the hint does not settle the question;
- once a company's officer or a person's spouse has been resolved to one node, blocks a different same-named node from inheriting that link by name.

## Testing and calibration without licensed data

Code: `backend/benchmarks/synthetic.py`, `backend/benchmarks/estimate_u.py`,
`backend/benchmarks/weights/`, `backend/tests/test_benchmarks.py`.

### Synthetic ground-truth benchmark

`benchmarks.synthetic` generates households, people and companies, builds grant
cases, plants six positive patterns (spouse-owned contractor, nickname disguise,
holding-company chain, straw owner, PI as officer, home-based shell) and four
negatives (surname coincidence, same building, same registered agent, clean),
adds realistic noise (nicknames, initials, honorifics, address formats, ZIP+4,
legal-suffix variants), runs the engine through a provider over the synthetic
world, and scores the result against the planted truth.

Results, 200 cases per run, roughly 900 counterparties each:

| Configuration | Precision | Recall | F1 | False-positive rate |
|---|---|---|---|---|
| Full registry and vital records, seed 7 | 1.000 | 0.980 | 0.990 | 0.000 |
| Same, seed 11 | 0.988 | 0.968 | 0.978 | 0.010 |
| No marriage or household records | 1.000 | 0.972 | 0.986 | 0.000 |
| Provider finds only 60% of entities | 1.000 | 0.633 | 0.775 | 0.000 |

Per pattern (seed 7): every positive pattern is confirmed at 97% or better,
indirect ownership percentages are recovered within a few points, 100% of
surname-only coincidences are routed to review rather than confirmed, and 95%
of same-building tenants and 94% of same-agent companies are correctly ignored.
The 60% coverage row is the important one for planning: the engine's recall is
bounded by data coverage, not by the algorithm, which is why the provider
connectors and agency data access matter more than further tuning.

The benchmark found and fixed six real engine defects before any live data was
touched: full-name collisions merging strangers, "Michael" fuzzy-matching
"Michelle", initials matching any name, near-identical org names counted as
hard evidence, two-word company names classified as people, and name-only
inheritance of resolved spouse and officer links.

```
cd backend
python -m benchmarks.synthetic --cases 200 --seed 7
python -m benchmarks.synthetic --no-vital-records
python -m benchmarks.synthetic --coverage 0.6
python -m benchmarks.synthetic --weights benchmarks/weights/colorado_sos_2026-11.json
```

### Coincidence rates measured from a real registry

`benchmarks.estimate_u` measures the u probabilities, how often two unrelated
parties share an identifier by chance, with no labels: the exact collision rate
across record pairs in a public corporate registry. It ships with a fetcher for
the Colorado Secretary of State open dataset and a generic CSV loader for any
other state.

Measured on 150,000 Colorado entities in good standing, pairs conditioned on
the same city:

| Signal | u assumed | u measured | Bits assumed | Bits measured |
|---|---|---|---|---|
| Same address incl. unit | 0.001 | 0.00051 | 9.2 | 10.2 |
| Same building, different unit | 0.01 | 0.00026 | 4.3 | 9.6 |
| Same registered agent | 0.08 | 0.0024 | 2.3 | 7.4 |
| Same formation date | 0.003 | 0.00024 | 7.6 | 11.3 |
| Formed same month | 0.03 | 0.0045 | 3.9 | 6.6 |
| Shared surname (agent individuals) | 0.004 | 0.00077 | 6.0 | 8.4 |

It also found 47 buildings hosting 50 or more entities each (1500 N Grant St in
Denver alone hosts 457), which feed the provider's registered-agent address
list, and a surname frequency table from 60,000 individual agents that broadly
agrees with the engine's built-in one.

The measured file is saved as `backend/benchmarks/weights/colorado_sos_2026-11.json`
and loads with `load_weights()` or `ConflictOfInterestTool(weights_path=...)`.

### Naive backtest on real federal award recipients

`benchmarks.backtest_usaspending` pulls federal grant recipients from the
public USAspending API with their SAM-registered parent organisation, address
and alternate names, and runs three tests. The committed report
(`backend/benchmarks/weights/usaspending_backtest_2026-11.json`) covers 160
child organisations, 121 of which had a distinct parent with an address; the
API throttled the pull before the full 250.

**1. Pick the registered parent out of a line-up, names and addresses only.**
Each child was shown its true parent plus six decoys, half from the same state.

| | Count |
|---|---|
| Child/parent pairs | 121 |
| True parent confirmed | 0 (3 before the recalibration below) |
| True parent in review band | 21 |
| Pairs where child and parent share a building | 5 |
| Decoy parents | 726 |
| Decoys confirmed (false flags) | 1 |

Recall is low because the data is thin, not because the engine is wrong:
only 5 of 121 real parent/child pairs share a building, so identifier
matching has nothing to work with for 96% of them. Those are exactly the
relationships the registry and vital-records providers exist to supply.
Name containment ("University of California" inside "University of California
Irvine") moved 12 pairs into review that would otherwise have been missed.
The decoy false-flag rate was 0.14%; the one remaining false flag shares an
exact address and a near-identical name with the child and is probably a
mislabelled affiliate rather than an engine error.

**2. Coincidence rates among unrelated grant recipients in the same city.**
This is the number the Colorado registry could not give: the population is
actual award recipients.

| Signal | Colorado registry | Grant recipients | Old default | New default |
|---|---|---|---|---|
| Same address incl. unit | 0.0005 | 0.021 | 0.001 | 0.005 |
| Same building | 0.00026 | 0.035 | 0.01 | 0.03 |

Two percent of unrelated same-city recipients share an exact address (state
agencies in capitol complexes, university departments, shared office towers).
Before recalibration, all three confirmed true parents and the decoy false
flag were confirmed on a shared address alone. The defaults were changed so
that a shared commercial address by itself lands in the review band (about
70%) and confirms only with corroboration; after the change those three true
parents sit in review alongside the others. Residential address sharing keeps
its full weight. The synthetic benchmark is unchanged by this (F1 0.980 and
0.992 on the two seeds).

**3. Alias resolution.** Of 4,097 alternate names recipients have used, the
normaliser now links 40% to the primary name (24% before abbreviation and
state-code expansion). Most of the rest are different agencies filed under one
registration ("IL ST OFFICE OF THE GOVERNOR" under the Illinois human services
DUNS), which no name logic should link.

```
cd backend
python -m benchmarks.backtest_usaspending --cache /path/to/cache --pages 30 --max-children 250
python -m benchmarks.backtest_usaspending --evaluate-only --cache /path/to/cache
```

### What the calibration does not settle

- **Context.** A registry-wide collision rate answers "two random Colorado companies". The pairs Veritas compares sit on one application and are chosen by one applicant, so coincidences are more common than the registry suggests. Conditioning on city narrows the gap. Running the calibrated weights on the synthetic benchmark leaves precision and recall unchanged but routes every same-building and same-agent pair to review, which is more records pulls than an investigator would want. The shipped defaults are therefore kept deliberately conservative for those two signals. The right u for them should be measured on real co-application pairs, for which USAspending.gov subaward files are the free source.
- **m values.** Registries say nothing about how often related parties share an identifier. Those need labelled or expectation-maximisation estimates, which the benchmark harness is built to accept once an agency pilot produces adjudicated cases.
- **Synthetic realism.** The synthetic world uses a small given-name vocabulary and more concentrated surnames than a real population, so it over-produces exact full-name collisions. That makes it a stress test for identity resolution, not an estimate of real-world false-positive rates.

## Running the tests

```
cd backend
python -m pytest tests -q
```
