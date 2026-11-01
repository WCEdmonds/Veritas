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
| Same address incl. unit | 9.2 | Commercial |
| Same private email domain | 9.5 | |
| Shared surname | 4.8 to 6.0 | Weighted by surname frequency: Smith scores lower than Hale |
| Same building, different unit | 5.6 | Multi-tenant |
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

## Running the tests

```
cd backend
python -m pytest tests/test_relationships.py -q
```
