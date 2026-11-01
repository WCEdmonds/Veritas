"""
Relationship Analysis Engine for grant conflict-of-interest detection.

Replaces name/keyword matching with three layers of evidence:

1. Entity resolution on identifiers.  Every party (applicant, key personnel,
   contractors, vendors, their officers and owners) is normalised into a set of
   canonical identifiers: addresses (USPS-style canonical form, unit split out),
   phones, emails, email domains, tax IDs, hashed bank accounts, IP/device IDs,
   registered agents, incorporation dates.  Two parties that share an
   identifier are linked, and the strength of that link depends on how
   discriminating the identifier is.  A shared bank account is near-proof; a
   shared registered agent is nearly meaningless because a handful of agents
   serve millions of companies.

2. Probabilistic scoring (Fellegi-Sunter record linkage).  Each matched signal
   contributes a log-likelihood ratio  log2(m / u)  where m is the probability
   the signal matches given the parties ARE related and u is the probability it
   matches by coincidence.  Signals are summed and combined with a prior to
   produce a posterior probability that the two parties are related.  Name
   evidence is included but weighted by surname frequency and fuzzy-matched
   with Jaro-Winkler plus a nickname table, so "Bill Hale" and "William Hale"
   match and two unrelated Smiths do not light up the board.

3. Graph link analysis.  Structural edges from corporate records (officer_of,
   owner_of with percentages, spouse_of, household_member_of) are combined
   with the inferred edges into one graph.  The engine searches for the best
   path from the applicant side to each counterparty, up to a configurable
   number of hops, so it finds "the PI's spouse is the managing member of the
   contractor" and "the vendor is owned by a holding company the PI owns 60%
   of", computes indirect ownership percentages, and exports the graph for
   visualisation.

Everything is explainable: every reported relationship carries the signals
that fired, their evidence weight in bits, the path through the graph, and
the Uniform Guidance (2 CFR 200) provision it implicates.

The engine is data-source agnostic.  A `RelationshipDataProvider` supplies
corporate registry, property and vital-records lookups; `MockRelationshipProvider`
ships a deterministic test world so the engine can be exercised without keys.
"""
from __future__ import annotations

import hashlib
import heapq
import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Protocol, Set, Tuple


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

_HONORIFICS = {"mr", "mrs", "ms", "miss", "dr", "prof", "professor", "rev", "hon", "sir", "dame"}
_NAME_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "phd", "md", "esq", "cpa", "mba", "jd", "dds", "rn"}
_ORG_SUFFIXES = {
    "llc", "l.l.c", "llp", "lp", "pllc", "pc", "plc", "inc", "incorporated", "corp", "corporation",
    "co", "company", "ltd", "limited", "gmbh", "sa", "ag", "bv", "nv", "pty", "trust", "foundation",
    "dba",
}
_ORG_STOPWORDS = {"the", "of", "and", "&", "a", "an", "for", "in", "at", "group", "services", "service",
                  "solutions", "holdings", "international", "global", "enterprises", "partners", "associates"}

_STREET_ABBR = {
    "street": "st", "avenue": "ave", "av": "ave", "road": "rd", "drive": "dr", "boulevard": "blvd",
    "lane": "ln", "court": "ct", "place": "pl", "terrace": "ter", "parkway": "pkwy", "highway": "hwy",
    "circle": "cir", "trail": "trl", "square": "sq", "plaza": "plz", "north": "n", "south": "s",
    "east": "e", "west": "w", "northeast": "ne", "northwest": "nw", "southeast": "se", "southwest": "sw",
}
_UNIT_WORDS = {"suite", "ste", "unit", "apt", "apartment", "#", "floor", "fl", "bldg", "building",
               "room", "rm", "no", "number", "office", "ofc"}

_PUBLIC_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com", "aol.com", "protonmail.com",
    "proton.me", "live.com", "msn.com", "me.com", "comcast.net", "att.net", "verizon.net",
}

# Common nickname -> formal given name.  Both directions are checked.
_NICKNAMES = {
    "bill": "william", "billy": "william", "will": "william", "liam": "william",
    "bob": "robert", "rob": "robert", "bobby": "robert", "robbie": "robert",
    "dick": "richard", "rick": "richard", "rich": "richard", "ricky": "richard",
    "jim": "james", "jimmy": "james", "jamie": "james",
    "jack": "john", "johnny": "john", "jon": "jonathan",
    "mike": "michael", "mikey": "michael", "mick": "michael",
    "dan": "daniel", "danny": "daniel",
    "dave": "david", "davey": "david",
    "tom": "thomas", "tommy": "thomas",
    "chris": "christopher", "topher": "christopher",
    "matt": "matthew", "matty": "matthew",
    "tony": "anthony", "ant": "anthony",
    "steve": "steven", "stephen": "steven",
    "joe": "joseph", "joey": "joseph",
    "ed": "edward", "eddie": "edward", "ted": "edward", "ned": "edward",
    "chuck": "charles", "charlie": "charles",
    "ben": "benjamin", "benny": "benjamin",
    "sam": "samuel", "sammy": "samuel",
    "alex": "alexander", "al": "albert",
    "andy": "andrew", "drew": "andrew",
    "nick": "nicholas", "nate": "nathan", "nat": "nathaniel",
    "pat": "patrick", "patty": "patricia", "trish": "patricia", "tricia": "patricia",
    "liz": "elizabeth", "beth": "elizabeth", "betty": "elizabeth", "eliza": "elizabeth", "lisa": "elizabeth",
    "kate": "katherine", "katie": "katherine", "kathy": "katherine", "kat": "katherine", "catherine": "katherine",
    "jen": "jennifer", "jenny": "jennifer", "jenn": "jennifer",
    "sue": "susan", "susie": "susan", "suzanne": "susan",
    "peggy": "margaret", "maggie": "margaret", "meg": "margaret", "marge": "margaret",
    "becky": "rebecca", "becca": "rebecca",
    "debbie": "deborah", "deb": "deborah",
    "cindy": "cynthia", "mandy": "amanda", "sandy": "sandra",
    "chrissy": "christina", "tina": "christina",
    "jess": "jessica", "jessie": "jessica",
    "steph": "stephanie", "vicky": "victoria", "tori": "victoria",
    "ellie": "eleanor", "nell": "eleanor", "ally": "allison", "abby": "abigail",
}

# Approximate share of the US population carrying a surname.  Used to weight
# surname matches: a shared rare surname is far more probative than a shared
# common one.  Names not listed fall back to a floor so that a surname match
# alone never exceeds the "review" band.
_SURNAME_FREQUENCY = {
    "smith": 0.0088, "johnson": 0.0069, "williams": 0.0056, "brown": 0.0050, "jones": 0.0049,
    "garcia": 0.0044, "miller": 0.0041, "davis": 0.0037, "rodriguez": 0.0036, "martinez": 0.0035,
    "hernandez": 0.0032, "lopez": 0.0030, "gonzalez": 0.0029, "wilson": 0.0028, "anderson": 0.0027,
    "thomas": 0.0026, "taylor": 0.0025, "moore": 0.0025, "jackson": 0.0024, "martin": 0.0024,
    "lee": 0.0024, "perez": 0.0023, "thompson": 0.0022, "white": 0.0022, "harris": 0.0021,
    "sanchez": 0.0021, "clark": 0.0020, "ramirez": 0.0020, "lewis": 0.0019, "robinson": 0.0019,
    "walker": 0.0019, "young": 0.0018, "allen": 0.0018, "king": 0.0018, "wright": 0.0017,
    "scott": 0.0017, "torres": 0.0017, "nguyen": 0.0017, "hill": 0.0016, "flores": 0.0016,
    "green": 0.0016, "adams": 0.0016, "nelson": 0.0015, "baker": 0.0015, "hall": 0.0015,
    "rivera": 0.0015, "campbell": 0.0014, "mitchell": 0.0014, "carter": 0.0014, "roberts": 0.0014,
}
_SURNAME_FREQUENCY_FLOOR = 0.004  # treat unknown surnames as "moderately common"


def _strip_punct(text: str) -> str:
    return re.sub(r"[^\w\s]", " ", text.lower()).strip()


@dataclass(frozen=True)
class PersonName:
    first: str
    middle: str
    last: str
    raw: str

    @property
    def canonical(self) -> str:
        return " ".join(p for p in (self.first, self.last) if p)

    @property
    def first_formal(self) -> str:
        return _NICKNAMES.get(self.first, self.first)


def parse_person_name(name: str) -> PersonName:
    """Parse 'Dr. Daniel R. Hale Jr.' or 'Hale, Daniel' into components."""
    raw = name.strip()
    text = raw
    if "," in text:
        head, _, tail = text.partition(",")
        tail_tokens = [t for t in _strip_punct(tail).split() if t]
        if tail_tokens and all(t in _NAME_SUFFIXES for t in tail_tokens):
            text = head                      # "Priya Raman, PhD"
        else:
            text = f"{tail} {head}"          # "Hale, Daniel"
    tokens = [t for t in _strip_punct(text).split() if t]
    tokens = [t for t in tokens if t not in _HONORIFICS]
    while tokens and tokens[-1] in _NAME_SUFFIXES:
        tokens.pop()
    if not tokens:
        return PersonName("", "", "", raw)
    if len(tokens) == 1:
        return PersonName(tokens[0], "", "", raw)
    first, last = tokens[0], tokens[-1]
    middle = " ".join(tokens[1:-1])
    return PersonName(first, middle, last, raw)


def canonical_org_name(name: str) -> str:
    """'The Northstar Analytics, L.L.C.' -> 'northstar analytics'."""
    tokens = [t for t in _strip_punct(name.replace(".", "")).split() if t]
    tokens = [t for t in tokens if t not in _ORG_SUFFIXES]
    core = [t for t in tokens if t not in _ORG_STOPWORDS]
    return " ".join(core or tokens)


@dataclass(frozen=True)
class CanonicalAddress:
    base: str      # street number + street + city/state/zip, unit removed
    unit: str      # suite / apt number, '' if none
    raw: str

    @property
    def full(self) -> str:
        return f"{self.base} unit {self.unit}" if self.unit else self.base


def canonical_address(address: str) -> Optional[CanonicalAddress]:
    if not address or not address.strip():
        return None
    text = address.lower().replace("#", " # ")
    text = re.sub(r"\b(\d{5})-\d{4}\b", r"\1", text)      # ZIP+4 -> ZIP
    text = re.sub(r"[^\w\s#]", " ", text)
    tokens = text.split()
    base: List[str] = []
    unit = ""
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in _UNIT_WORDS and i + 1 < len(tokens):
            unit = tokens[i + 1]
            i += 2
            continue
        # "Suite 400B" sometimes arrives glued: "ste400"
        m = re.match(r"^(ste|apt|unit|fl|rm)(\d+\w*)$", tok)
        if m:
            unit = m.group(2)
            i += 1
            continue
        tok = _STREET_ABBR.get(tok, tok)
        # 5+4 zip -> 5
        if re.match(r"^\d{5}\d{4}$", tok):
            tok = tok[:5]
        base.append(tok)
        i += 1
    return CanonicalAddress(" ".join(base), unit, address.strip())


def canonical_phone(phone: str) -> Optional[str]:
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits if len(digits) == 10 else (digits or None)


def canonical_email(email: str) -> Optional[Tuple[str, str]]:
    """Returns (normalised address, domain) or None."""
    if not email or "@" not in email:
        return None
    local, _, domain = email.strip().lower().rpartition("@")
    if domain in {"gmail.com", "googlemail.com"}:
        local = local.split("+")[0].replace(".", "")
        domain = "gmail.com"
    else:
        local = local.split("+")[0]
    return f"{local}@{domain}", domain


def canonical_tax_id(tax_id: str) -> Optional[str]:
    digits = re.sub(r"\D", "", tax_id or "")
    return digits or None


def hash_bank_account(routing: str, account: str) -> str:
    """Bank identifiers are never stored in the clear; we match on a salted hash."""
    digits = re.sub(r"\D", "", f"{routing}{account}")
    return hashlib.sha256(f"veritas-bank:{digits}".encode()).hexdigest()[:24]


def canonical_domain(value: str) -> Optional[str]:
    if not value:
        return None
    v = value.strip().lower()
    v = re.sub(r"^https?://", "", v)
    v = v.split("/")[0]
    v = v[4:] if v.startswith("www.") else v
    return v or None


def _parse_date(value: Any) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(str(value)[:10], fmt).date()
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# String similarity
# ---------------------------------------------------------------------------

def jaro_winkler(s1: str, s2: str, prefix_scale: float = 0.1) -> float:
    if s1 == s2:
        return 1.0
    len1, len2 = len(s1), len(s2)
    if not len1 or not len2:
        return 0.0
    match_distance = max(len1, len2) // 2 - 1
    s1_matches = [False] * len1
    s2_matches = [False] * len2
    matches = 0
    for i in range(len1):
        lo = max(0, i - match_distance)
        hi = min(i + match_distance + 1, len2)
        for j in range(lo, hi):
            if not s2_matches[j] and s1[i] == s2[j]:
                s1_matches[i] = s2_matches[j] = True
                matches += 1
                break
    if matches == 0:
        return 0.0
    transpositions = 0
    k = 0
    for i in range(len1):
        if s1_matches[i]:
            while not s2_matches[k]:
                k += 1
            if s1[i] != s2[k]:
                transpositions += 1
            k += 1
    transpositions //= 2
    jaro = (matches / len1 + matches / len2 + (matches - transpositions) / matches) / 3.0
    prefix = 0
    for a, b in zip(s1, s2):
        if a == b and prefix < 4:
            prefix += 1
        else:
            break
    return jaro + prefix * prefix_scale * (1.0 - jaro)


def given_names_match(a: str, b: str) -> bool:
    """'Bill' vs 'William', 'Jen' vs 'Jennifer', initial vs full name."""
    if not a or not b:
        return False
    if a == b:
        return True
    fa, fb = _NICKNAMES.get(a, a), _NICKNAMES.get(b, b)
    if fa == fb:
        return True
    if len(a) == 1 or len(b) == 1:
        return a[0] == b[0]
    # 0.95 tolerates a transposed letter but keeps Michael/Michelle, Marion/Marian apart.
    return jaro_winkler(fa, fb) >= 0.95


def same_person_score(a: PersonName, b: PersonName) -> float:
    """0..1 likelihood that two name strings refer to the same individual."""
    if not a.last or not b.last:
        return 0.0
    last_sim = jaro_winkler(a.last, b.last)
    if last_sim < 0.88:
        return 0.0
    if len(a.first) == 1 or len(b.first) == 1:
        # "S. Ibarra" vs "Samuel Ibarra": an initial is compatible with many names.
        # Capped below the same-person threshold so it can only ever be soft evidence.
        return 0.75 * last_sim if given_names_match(a.first, b.first) else 0.0
    if given_names_match(a.first, b.first):
        return min(1.0, 0.6 + 0.4 * last_sim)
    # Could be a maiden-name or data-entry situation; weak.
    return 0.3 * last_sim if jaro_winkler(a.first, b.first) > 0.8 else 0.0


def org_name_similarity(a: str, b: str) -> float:
    ca, cb = canonical_org_name(a), canonical_org_name(b)
    if not ca or not cb:
        return 0.0
    if ca == cb:
        return 1.0
    ta, tb = set(ca.split()), set(cb.split())
    jaccard = len(ta & tb) / max(1, len(ta | tb))
    return max(jaccard, jaro_winkler(ca, cb) if jaro_winkler(ca, cb) > 0.93 else 0.0)


def surname_frequency(last: str) -> float:
    return max(_SURNAME_FREQUENCY.get(last, 0.0), _SURNAME_FREQUENCY_FLOOR)


# ---------------------------------------------------------------------------
# Entity model
# ---------------------------------------------------------------------------

@dataclass
class Ownership:
    owner_name: str
    percent: float  # 0..100


@dataclass
class EntityRecord:
    """Everything we know about one party.  All list fields hold raw values; the
    engine canonicalises them."""
    name: str
    kind: str = "organization"            # "organization" | "person"
    role: str = "counterparty"            # applicant | key_personnel | contractor | vendor | officer | owner | related
    addresses: List[str] = field(default_factory=list)
    address_types: Dict[str, str] = field(default_factory=dict)   # raw address -> residential|commercial|registered_agent|virtual_office|po_box
    phones: List[str] = field(default_factory=list)
    emails: List[str] = field(default_factory=list)
    websites: List[str] = field(default_factory=list)
    tax_ids: List[str] = field(default_factory=list)
    bank_account_hashes: List[str] = field(default_factory=list)
    ip_addresses: List[str] = field(default_factory=list)
    device_ids: List[str] = field(default_factory=list)
    registered_agent: Optional[str] = None
    incorporation_date: Optional[Any] = None
    officers: List[str] = field(default_factory=list)              # person names (orgs)
    owners: List[Ownership] = field(default_factory=list)          # owners (orgs)
    spouse: Optional[str] = None                                   # persons
    household_members: List[str] = field(default_factory=list)     # persons
    employer: Optional[str] = None                                 # persons
    sources: List[str] = field(default_factory=list)
    lookup_hint: Optional[str] = None     # an address to disambiguate a provider lookup; never treated as the party's own identifier
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            self.id = entity_id(self.name, self.kind)

    def merge(self, other: "EntityRecord") -> None:
        """Fold provider enrichment into the submitted record."""
        for attr in ("addresses", "phones", "emails", "websites", "tax_ids", "bank_account_hashes",
                     "ip_addresses", "device_ids", "officers", "household_members", "sources"):
            mine: List[str] = getattr(self, attr)
            for v in getattr(other, attr):
                if v not in mine:
                    mine.append(v)
        for raw, typ in other.address_types.items():
            self.address_types.setdefault(raw, typ)
        seen = {o.owner_name.lower() for o in self.owners}
        for o in other.owners:
            if o.owner_name.lower() not in seen:
                self.owners.append(o)
        self.registered_agent = self.registered_agent or other.registered_agent
        self.incorporation_date = self.incorporation_date or other.incorporation_date
        self.spouse = self.spouse or other.spouse
        self.employer = self.employer or other.employer


def person_key(name: str) -> str:
    """Nickname-resolved 'first last' key: 'Dr. Dan Hale' and 'Daniel Hale' collide."""
    pn = parse_person_name(name)
    return " ".join(p for p in (pn.first_formal, pn.last) if p)


def entity_id(name: str, kind: str) -> str:
    key = person_key(name) if kind == "person" else canonical_org_name(name)
    return f"{kind[:3]}:{key or name.strip().lower()}"


# Signals strong enough on their own to confirm a relationship.  Everything
# else is "soft" and can only ever route a pair to the review band, where the
# autonomous resolver fetches more evidence.
HARD_SIGNALS = {
    "same_tax_id", "same_bank_account", "same_phone", "same_email", "same_device", "same_ip_address",
    "same_residential_address", "same_address", "same_private_domain", "officer_overlap", "common_owner",
    "same_org_name", "same_person_name", "marriage_record", "household_record", "is_officer_of",
    "is_owner_of", "is_employed_by", "registry_officer", "registry_ownership", "application_disclosure",
}


# ---------------------------------------------------------------------------
# Signals and scoring
# ---------------------------------------------------------------------------

@dataclass
class Signal:
    kind: str
    m: float                 # P(signal | related)
    u: float                 # P(signal | unrelated)
    description: str
    value: str = ""          # the shared identifier (redacted where sensitive)

    @property
    def llr_bits(self) -> float:
        return math.log2(self.m / self.u)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal": self.kind,
            "description": self.description,
            "shared_value": self.value,
            "evidence_bits": round(self.llr_bits, 2),
        }


@dataclass
class Edge:
    source: str
    target: str
    kind: str                       # relationship type
    probability: float
    signals: List[Signal] = field(default_factory=list)
    structural: bool = False        # from registry/vital records rather than inferred
    detail: Dict[str, Any] = field(default_factory=dict)

    @property
    def llr_bits(self) -> float:
        return sum(s.llr_bits for s in self.signals)

    def evidence(self) -> List[str]:
        return [s.description for s in self.signals]


# (m, u) per signal: m = P(match | related), u = P(match | unrelated).
# These defaults are priors.  `benchmarks/estimate_u.py` measures u directly from
# a public corporate registry; `benchmarks/synthetic.py` measures the resulting
# precision/recall; `load_weights()` swaps calibrated values in.
DEFAULT_WEIGHTS: Dict[str, Tuple[float, float]] = {
    "same_tax_id": (0.98, 0.00001),
    "same_bank_account": (0.95, 0.00001),
    "same_phone": (0.85, 0.0001),
    "same_email": (0.90, 0.00001),
    "same_private_domain": (0.70, 0.001),
    "same_ip_address": (0.80, 0.001),
    "same_device": (0.85, 0.0001),
    "same_residential_address": (0.80, 0.0002),
    "same_address": (0.60, 0.001),
    "same_building": (0.20, 0.01),              # related parties usually share the suite, not just the tower
    "same_mail_drop_address": (0.60, 0.10),
    "officer_overlap": (0.90, 0.0001),
    "common_owner": (0.92, 0.0001),
    "same_registered_agent": (0.40, 0.08),
    "same_incorporation_date": (0.60, 0.003),
    "incorporated_same_month": (0.45, 0.03),
    "same_org_name": (0.90, 0.0001),
    "similar_org_name": (0.50, 0.01),
    "same_person_name": (0.90, 0.0001),
    "same_name_different_identifiers": (0.30, 0.02),   # same full name but disjoint addresses/phones: probably two people
    "same_name_unverified": (0.60, 0.005),             # same full name, one side has no identifiers to check against
    "shared_surname": (0.25, 0.004),            # u is replaced by the surname's own frequency
    "officer_shares_surname": (0.25, 0.004),    # u is replaced by the surname's own frequency
    "marriage_record": (0.98, 0.00001),
    "household_record": (0.90, 0.0001),
    "is_officer_of": (0.95, 0.0001),
    "is_owner_of": (0.95, 0.0001),
    "is_employed_by": (0.85, 0.001),
    "formed_near_application": (0.50, 0.10),
    "registry_officer": (0.98, 0.0001),
    "registry_ownership": (0.98, 0.0001),
    "application_disclosure": (0.99, 0.0001),
}

Weights = Dict[str, Tuple[float, float]]


def _sig(kind: str, weights: Optional[Weights], u_override: Optional[float], description: str, value: str = "") -> Signal:
    m, u = (weights or DEFAULT_WEIGHTS).get(kind, DEFAULT_WEIGHTS[kind])
    if u_override is not None:
        u = max(u_override, 1e-6)
    return Signal(kind, m, u, description, value)


def load_weights(path: str) -> Weights:
    """Read calibrated weights written by the benchmark tooling.
    Format: {"signal_kind": {"m": 0.8, "u": 0.0002}, ...}; missing kinds keep defaults."""
    import json
    with open(path) as fh:
        raw = json.load(fh)
    weights = dict(DEFAULT_WEIGHTS)
    for kind, mu in raw.items():
        if kind in weights and isinstance(mu, dict) and "m" in mu and "u" in mu:
            weights[kind] = (float(mu["m"]), float(mu["u"]))
    return weights


def posterior_probability(llr_bits: float, prior: float) -> float:
    prior_logodds = math.log2(prior / (1.0 - prior))
    logodds = prior_logodds + llr_bits
    if logodds > 60:
        return 1.0
    if logodds < -60:
        return 0.0
    return 1.0 / (1.0 + 2.0 ** (-logodds))


def _address_signal(a: EntityRecord, b: EntityRecord, provider: "RelationshipDataProvider",
                    weights: Optional[Weights] = None) -> List[Signal]:
    signals: List[Signal] = []
    a_addrs = {ca.full: (ca, raw) for raw in a.addresses if (ca := canonical_address(raw))}
    b_addrs = {cb.full: (cb, raw) for raw in b.addresses if (cb := canonical_address(raw))}
    seen_bases: Set[str] = set()

    def addr_type(rec: EntityRecord, raw: str, canon: CanonicalAddress) -> str:
        typ = rec.address_types.get(raw, "")
        if not typ and provider.is_registered_agent_address(canon.base):
            typ = "registered_agent"
        return typ or "unknown"

    for key, (ca, raw_a) in a_addrs.items():
        if key in b_addrs:
            cb, raw_b = b_addrs[key]
            types = {addr_type(a, raw_a, ca), addr_type(b, raw_b, cb)}
            seen_bases.add(ca.base)
            if types & {"registered_agent", "virtual_office", "po_box"}:
                signals.append(_sig("same_mail_drop_address", weights, None, f"Both use the same registered-agent / mail-drop address ({raw_a})", raw_a))
            elif "residential" in types:
                signals.append(_sig("same_residential_address", weights, None, f"Both tied to the same residential address ({raw_a})", raw_a))
            else:
                signals.append(_sig("same_address", weights, None, f"Both tied to the same address including unit ({raw_a})", raw_a))
    # Same building, different (or missing) unit
    for ca, raw_a in a_addrs.values():
        if ca.base in seen_bases:
            continue
        for cb, raw_b in b_addrs.values():
            if ca.base == cb.base and ca.full != cb.full:
                seen_bases.add(ca.base)
                types = {addr_type(a, raw_a, ca), addr_type(b, raw_b, cb)}
                if types & {"registered_agent", "virtual_office", "po_box"}:
                    signals.append(_sig("same_mail_drop_address", weights, None, f"Both use the same registered-agent / mail-drop building ({raw_a})", raw_a))
                elif "residential" in types:
                    signals.append(_sig("same_residential_address", weights, None, f"Both tied to the same residential address ({raw_a})", raw_a))
                else:
                    signals.append(_sig("same_building", weights, None, f"Both located in the same building, different unit ({raw_a} / {raw_b})", raw_a))
                break
    return signals


def compare_entities(a: EntityRecord, b: EntityRecord, provider: "RelationshipDataProvider",
                     application_date: Optional[date] = None,
                     weights: Optional[Weights] = None) -> List[Signal]:
    """All attribute-level signals between two parties."""
    signals: List[Signal] = []
    weights = weights or DEFAULT_WEIGHTS

    # Hard identifiers --------------------------------------------------------
    a_tax = {canonical_tax_id(t) for t in a.tax_ids} - {None}
    b_tax = {canonical_tax_id(t) for t in b.tax_ids} - {None}
    for t in a_tax & b_tax:
        signals.append(_sig("same_tax_id", weights, None, "Identical tax identification number (EIN/TIN)",
                              f"***{t[-4:]}"))

    for h in set(a.bank_account_hashes) & set(b.bank_account_hashes):
        signals.append(_sig("same_bank_account", weights, None, "Payments routed to the same bank account", f"hash:{h[:8]}"))

    a_ph = {canonical_phone(p) for p in a.phones} - {None}
    b_ph = {canonical_phone(p) for p in b.phones} - {None}
    for p in a_ph & b_ph:
        signals.append(_sig("same_phone", weights, None, f"Same contact phone number (…{p[-4:]})", f"…{p[-4:]}"))

    a_em = {canonical_email(e) for e in a.emails} - {None}
    b_em = {canonical_email(e) for e in b.emails} - {None}
    a_em_addr = {e[0] for e in a_em}
    b_em_addr = {e[0] for e in b_em}
    for e in a_em_addr & b_em_addr:
        signals.append(_sig("same_email", weights, None, f"Same email address ({e})", e))
    if not (a_em_addr & b_em_addr):
        a_dom = {e[1] for e in a_em} | {canonical_domain(w) for w in a.websites} - {None}
        b_dom = {e[1] for e in b_em} | {canonical_domain(w) for w in b.websites} - {None}
        for d in (a_dom & b_dom) - _PUBLIC_EMAIL_DOMAINS - {None}:
            signals.append(_sig("same_private_domain", weights, None, f"Email/web presence on the same private domain ({d})", d))

    for ip in set(a.ip_addresses) & set(b.ip_addresses):
        signals.append(_sig("same_ip_address", weights, None, f"Submissions from the same IP address ({ip})", ip))
    for dev in set(a.device_ids) & set(b.device_ids):
        signals.append(_sig("same_device", weights, None, "Submissions from the same device fingerprint", dev[:8]))

    signals.extend(_address_signal(a, b, provider, weights))

    # Corporate structure signals ---------------------------------------------
    if a.kind == "organization" and b.kind == "organization":
        a_off = {parse_person_name(o).canonical for o in a.officers} - {""}
        b_off = {parse_person_name(o).canonical for o in b.officers} - {""}
        for person in a_off & b_off:
            signals.append(_sig("officer_overlap", weights, None, f"{person.title()} is an officer/director of both organizations", person))
        a_own = {parse_person_name(o.owner_name).canonical for o in a.owners} | \
                {canonical_org_name(o.owner_name) for o in a.owners}
        b_own = {parse_person_name(o.owner_name).canonical for o in b.owners} | \
                {canonical_org_name(o.owner_name) for o in b.owners}
        for owner in (a_own & b_own) - {""} - (a_off & b_off):
            signals.append(_sig("common_owner", weights, None, f"{owner.title()} holds ownership in both organizations", owner))

        if a.registered_agent and b.registered_agent and \
                canonical_org_name(a.registered_agent) == canonical_org_name(b.registered_agent):
            signals.append(_sig("same_registered_agent", weights, None, f"Same registered agent ({a.registered_agent}); weak on its own",
                                  a.registered_agent))

        da, db = _parse_date(a.incorporation_date), _parse_date(b.incorporation_date)
        if da and db:
            if da == db:
                signals.append(_sig("same_incorporation_date", weights, None, f"Both formed on the same day ({da.isoformat()})", da.isoformat()))
            elif abs((da - db).days) <= 30:
                signals.append(_sig("incorporated_same_month", weights, None, f"Formed within {abs((da - db).days)} days of each other", ""))

        sim = org_name_similarity(a.name, b.name)
        if canonical_org_name(a.name) == canonical_org_name(b.name):
            signals.append(_sig("same_org_name", weights, None, f"Organization names resolve to the same canonical name ('{canonical_org_name(a.name)}')",
                                  canonical_org_name(a.name)))
        elif sim >= 0.6:
            signals.append(_sig("similar_org_name", weights, None, f"Organization names share most tokens ('{a.name}' vs '{b.name}')", ""))

    # Person-to-person signals ------------------------------------------------
    if a.kind == "person" and b.kind == "person":
        pa, pb = parse_person_name(a.name), parse_person_name(b.name)
        sp = same_person_score(pa, pb)
        if sp >= 0.9 and identity_conflict(a, b):
            signals.append(_sig("same_name_different_identifiers", weights, None,
                                f"Same name ('{a.name}' / '{b.name}') but different addresses and phones; likely two individuals",
                                pa.canonical))
        elif sp >= 0.9 and not (has_identifiers(a) and has_identifiers(b)):
            signals.append(_sig("same_name_unverified", weights, None,
                                f"Same name ('{a.name}' / '{b.name}') but no identifiers to confirm they are one person",
                                pa.canonical))
        elif sp >= 0.9:
            signals.append(_sig("same_person_name", weights, None, f"Names resolve to the same individual ('{a.name}' / '{b.name}')", pa.canonical))
        elif sp > 0:
            # Initial-only match: soft, weighted like a shared surname.
            freq = surname_frequency(pa.last)
            signals.append(_sig("shared_surname", weights, freq,
                                f"'{a.name}' is compatible with '{b.name}' (initial match, surname '{pa.last.title()}'); not conclusive",
                                pa.last))
        elif pa.last and pb.last and jaro_winkler(pa.last, pb.last) >= 0.95 and not given_names_match(pa.first, pb.first):
            freq = surname_frequency(pa.last)
            signals.append(_sig("shared_surname", weights, freq, f"Shared surname '{pa.last.title()}' (≈{freq*100:.2f}% of population)", pa.last))
        if a.spouse and parse_person_name(a.spouse).canonical == pb.canonical or \
                b.spouse and parse_person_name(b.spouse).canonical == pa.canonical:
            signals.append(_sig("marriage_record", weights, None, "Marriage record links the two individuals", ""))
        a_hh = {parse_person_name(h).canonical for h in a.household_members}
        b_hh = {parse_person_name(h).canonical for h in b.household_members}
        if (pb.canonical in a_hh or pa.canonical in b_hh) and not any(s.kind == "marriage_record" for s in signals):
            signals.append(_sig("household_record", weights, None, "Public records place both individuals in the same household", ""))

    # Person-to-organization signals -------------------------------------------
    person, org = (a, b) if a.kind == "person" and b.kind == "organization" else \
                  (b, a) if b.kind == "person" and a.kind == "organization" else (None, None)
    if person and org:
        pn = parse_person_name(person.name)
        for officer in org.officers:
            if same_person_score(pn, parse_person_name(officer)) >= 0.9 and not identity_conflict(person, org):
                signals.append(_sig("is_officer_of", weights, None, f"{person.name} is listed as an officer/director of {org.name}", officer))
                break
        for owner in org.owners:
            if same_person_score(pn, parse_person_name(owner.owner_name)) >= 0.9:
                signals.append(_sig("is_owner_of", weights, None, f"{person.name} holds {owner.percent:.0f}% ownership of {org.name}", owner.owner_name))
                break
        if person.employer and org_name_similarity(person.employer, org.name) >= 0.95:
            signals.append(_sig("is_employed_by", weights, None, f"{person.name} is employed by {org.name}", ""))
        # Surname of the person appears in org officers (possible family-run vendor)
        for officer in org.officers:
            on = parse_person_name(officer)
            if pn.last and on.last == pn.last and not given_names_match(pn.first, on.first):
                freq = surname_frequency(pn.last)
                signals.append(_sig("officer_shares_surname", weights, freq, f"Officer '{officer}' of {org.name} shares surname '{pn.last.title()}' with {person.name}",
                                      pn.last))
                break

    # Timing relative to the application --------------------------------------
    # Only meaningful for an applicant-side <-> counterparty pair; otherwise a
    # newly formed contractor would light up against every other node.
    if application_date:
        applicant_side_roles = {"applicant", "key_personnel"}
        counterparty_roles = {"contractor", "vendor"}
        for rec, other in ((a, b), (b, a)):
            d = _parse_date(rec.incorporation_date)
            if d and rec.kind == "organization" and rec.role in counterparty_roles and other.role in applicant_side_roles:
                delta = (application_date - d).days
                if -30 <= delta <= 90:
                    signals.append(_sig("formed_near_application", weights, None, f"{rec.name} was formed {abs(delta)} days {'before' if delta >= 0 else 'after'} the application date",
                                          d.isoformat()))
    dedup: Dict[Tuple[str, str], Signal] = {}
    for s in signals:
        dedup.setdefault((s.kind, s.value), s)
    return list(dedup.values())


def has_identifiers(rec: EntityRecord) -> bool:
    return bool(rec.addresses or rec.phones or rec.emails or rec.tax_ids or rec.bank_account_hashes)


def identity_conflict(a: EntityRecord, b: EntityRecord) -> bool:
    """True when two same-named person records carry incompatible identifiers:
    both have addresses with no building in common and no phone in common.
    Such records are kept as separate nodes instead of being merged."""
    if a.kind != "person" or b.kind != "person":
        return False
    a_bases = {c.base for r in a.addresses if (c := canonical_address(r))}
    b_bases = {c.base for r in b.addresses if (c := canonical_address(r))}
    if not a_bases or not b_bases or (a_bases & b_bases):
        return False
    a_ph = {canonical_phone(p) for p in a.phones} - {None}
    b_ph = {canonical_phone(p) for p in b.phones} - {None}
    if a_ph & b_ph:
        return False
    a_em = {e[0] for e in ({canonical_email(x) for x in a.emails} - {None})}
    b_em = {e[0] for e in ({canonical_email(x) for x in b.emails} - {None})}
    return not (a_em & b_em)


def classify_signals(signals: List[Signal], a: EntityRecord, b: EntityRecord) -> str:
    kinds = {s.kind for s in signals}
    if "marriage_record" in kinds:
        return "spouse"
    if "same_person_name" in kinds:
        return "same_person"
    if "household_record" in kinds:
        return "household"
    if "same_tax_id" in kinds or "same_org_name" in kinds:
        return "same_entity"
    if "is_owner_of" in kinds:
        return "ownership_interest"
    if "is_officer_of" in kinds:
        return "officer_of"
    if "is_employed_by" in kinds:
        return "employed_by"
    if "same_residential_address" in kinds and "shared_surname" in kinds:
        return "household"
    if "same_residential_address" in kinds and a.kind == "person" and b.kind == "person":
        return "cohabitant"
    if "officer_overlap" in kinds or "common_owner" in kinds or "same_bank_account" in kinds:
        return "common_control"
    if kinds & {"same_phone", "same_email", "same_device", "same_ip_address"}:
        return "operational_control"
    if kinds & {"same_address", "same_residential_address", "same_building"} and \
            kinds & {"same_incorporation_date", "incorporated_same_month", "same_registered_agent", "formed_near_application"}:
        return "shell_cluster"
    if kinds & {"same_address", "same_residential_address"}:
        return "co_located"
    if "same_building" in kinds:
        return "same_building"
    if "same_private_domain" in kinds:
        return "operational_control"
    if kinds & {"shared_surname", "officer_shares_surname"}:
        return "possible_family"
    if "similar_org_name" in kinds:
        return "possible_affiliate"
    return "weak_association"


# ---------------------------------------------------------------------------
# Data provider protocol
# ---------------------------------------------------------------------------

class RelationshipDataProvider(Protocol):
    """Supplies external records.  Implementations: OpenCorporates, state SoS
    registries, county recorder/property, LexisNexis, vital records, or the
    agency's own vendor master."""

    async def enrich_organization(self, name: str, tax_id: Optional[str] = None,
                                  address: Optional[str] = None) -> Optional[EntityRecord]: ...

    async def enrich_person(self, name: str, address: Optional[str] = None) -> Optional[EntityRecord]:
        """`address` is a disambiguation hint (the party's own address if known, otherwise the
        address of the company that listed them).  When several people share the name,
        return the one whose records touch that address.  If the hint does not settle it,
        return None rather than guess: an unenriched node costs recall, a wrong person
        costs a false accusation.  Never fabricate the hint into the returned record."""
        ...

    def is_registered_agent_address(self, canonical_base_address: str) -> bool: ...


class NullProvider:
    """No external data; the engine works purely from submitted records."""

    async def enrich_organization(self, name, tax_id=None, address=None):
        return None

    async def enrich_person(self, name, address=None):
        return None

    def is_registered_agent_address(self, canonical_base_address: str) -> bool:
        return False


class MockRelationshipProvider:
    """Deterministic test world.  Unknown names return None so the engine
    degrades gracefully to submitted-data-only analysis."""

    REGISTERED_AGENT_ADDRESSES = {
        canonical_address("1209 Orange Street, Wilmington, DE 19801").base,          # CT Corporation
        canonical_address("251 Little Falls Drive, Wilmington, DE 19808").base,      # CSC
        canonical_address("30 N Gould St Ste R, Sheridan, WY 82801").base,           # Registered Agents Inc
        canonical_address("1942 Broadway St STE 314C, Boulder, CO 80302").base,      # Northwest RA
    }

    def __init__(self) -> None:
        hale_home = "4821 Juniper Ct, Boulder, CO 80301"
        self._orgs: Dict[str, EntityRecord] = {}
        self._people: Dict[str, EntityRecord] = {}

        def org(rec: EntityRecord) -> None:
            self._orgs[canonical_org_name(rec.name)] = rec

        def person(rec: EntityRecord) -> None:
            self._people[person_key(rec.name)] = rec

        # --- The Hale scenario: PI's spouse runs the "independent" contractor,
        #     and a vendor is owned through a family holding company.
        person(EntityRecord(
            name="Daniel Hale", kind="person", role="related",
            addresses=[hale_home], address_types={hale_home: "residential"},
            phones=["303-555-0142"], emails=["dhale@meridianresearch.org"],
            spouse="Jennifer Hale", household_members=["Jennifer Hale"],
            employer="Meridian Research Group", sources=["county_recorder", "vital_records"],
        ))
        person(EntityRecord(
            name="Jennifer Hale", kind="person", role="related",
            addresses=[hale_home], address_types={hale_home: "residential"},
            phones=["303-555-0142"], emails=["jhale@northstar-analytics.com"],
            spouse="Daniel Hale", household_members=["Daniel Hale"],
            sources=["county_recorder", "vital_records"],
        ))
        person(EntityRecord(
            name="Marcus Oyelaran", kind="person", role="related",
            addresses=["77 Pine St, Longmont, CO 80501"], address_types={"77 Pine St, Longmont, CO 80501": "residential"},
            sources=["county_recorder"],
        ))
        person(EntityRecord(
            name="Patricia Hale", kind="person", role="related",
            addresses=["310 Elm Ave, Fort Collins, CO 80521"],
            address_types={"310 Elm Ave, Fort Collins, CO 80521": "residential"},
            sources=["county_recorder"],
        ))
        org(EntityRecord(
            name="Meridian Research Group", kind="organization", role="applicant",
            addresses=["1200 Research Pkwy Suite 400, Boulder, CO 80301"],
            address_types={"1200 Research Pkwy Suite 400, Boulder, CO 80301": "commercial"},
            phones=["303-555-0100"], websites=["meridianresearch.org"], tax_ids=["84-1234567"],
            registered_agent="Registered Agents Inc", incorporation_date="2014-03-02",
            officers=["Daniel Hale", "Priya Raman"], sources=["co_sos"],
        ))
        org(EntityRecord(
            name="Northstar Analytics LLC", kind="organization", role="contractor",
            addresses=[hale_home], address_types={hale_home: "residential"},
            phones=["303-555-0142"], emails=["contact@northstar-analytics.com"],
            websites=["northstar-analytics.com"], tax_ids=["84-7654321"],
            registered_agent="Registered Agents Inc", incorporation_date="2025-09-12",
            officers=["Jennifer Hale"], owners=[Ownership("Jennifer Hale", 100.0)], sources=["co_sos"],
        ))
        org(EntityRecord(
            name="Hale Family Holdings LLC", kind="organization", role="related",
            addresses=[hale_home], address_types={hale_home: "residential"},
            tax_ids=["84-2222222"], registered_agent="Registered Agents Inc", incorporation_date="2019-06-01",
            owners=[Ownership("Daniel Hale", 60.0), Ownership("Jennifer Hale", 40.0)],
            bank_account_hashes=[hash_bank_account("102000021", "4455667788")], sources=["co_sos"],
        ))
        org(EntityRecord(
            name="Summit Field Services Inc", kind="organization", role="vendor",
            addresses=["900 Industrial Way, Longmont, CO 80501"],
            address_types={"900 Industrial Way, Longmont, CO 80501": "commercial"},
            phones=["720-555-0199"], tax_ids=["84-3333333"], registered_agent="CT Corporation System",
            incorporation_date="2021-02-15", officers=["Marcus Oyelaran"],
            owners=[Ownership("Hale Family Holdings LLC", 100.0)],
            bank_account_hashes=[hash_bank_account("102000021", "4455667788")], sources=["co_sos"],
        ))
        org(EntityRecord(
            name="Front Range Statistical Consulting LLC", kind="organization", role="contractor",
            addresses=["310 Elm Ave, Fort Collins, CO 80521"],
            address_types={"310 Elm Ave, Fort Collins, CO 80521": "residential"},
            tax_ids=["84-4444444"], registered_agent="Registered Agents Inc", incorporation_date="2018-11-20",
            officers=["Patricia Hale"], owners=[Ownership("Patricia Hale", 100.0)], sources=["co_sos"],
        ))
        org(EntityRecord(
            name="Dell Technologies Inc", kind="organization", role="vendor",
            addresses=["1 Dell Way, Round Rock, TX 78682"],
            address_types={"1 Dell Way, Round Rock, TX 78682": "commercial"},
            tax_ids=["74-2487834"], registered_agent="Registered Agents Inc", incorporation_date="1984-05-03",
            officers=["Michael Dell"], sources=["tx_sos"],
        ))

    async def enrich_organization(self, name, tax_id=None, address=None):
        rec = self._orgs.get(canonical_org_name(name))
        if rec is None and tax_id:
            t = canonical_tax_id(tax_id)
            rec = next((r for r in self._orgs.values() if t in {canonical_tax_id(x) for x in r.tax_ids}), None)
        return rec

    async def enrich_person(self, name, address=None):
        return self._people.get(person_key(name))

    def is_registered_agent_address(self, canonical_base_address: str) -> bool:
        return canonical_base_address in self.REGISTERED_AGENT_ADDRESSES


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

@dataclass
class RelationshipFinding:
    counterparty: str
    counterparty_role: str
    relationship_type: str
    probability: float
    evidence_bits: float
    direct: bool
    path: List[str]                       # entity names along the path
    path_description: str
    evidence: List[str]
    signals: List[Dict[str, Any]]
    indirect_ownership_percent: float
    uniform_guidance: List[str]
    self_dealing: bool
    immediate_family: bool
    band: str                             # "confirmed" | "review" | "weak"


@dataclass
class RelationshipAnalysis:
    findings: List[RelationshipFinding]
    review_recommended: List[RelationshipFinding]
    graph: Dict[str, Any]
    entity_count: int
    edge_count: int
    method: str = "fellegi_sunter_record_linkage+graph_path_analysis"


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class RelationshipEngine:
    def __init__(self, provider: Optional[RelationshipDataProvider] = None, prior_related: float = 0.02,
                 report_threshold: float = 0.80, review_threshold: float = 0.35, max_hops: int = 3,
                 weights: Optional[Weights] = None) -> None:
        self.provider = provider or NullProvider()
        self.weights: Weights = dict(weights) if weights else dict(DEFAULT_WEIGHTS)
        self.prior = prior_related
        self.report_threshold = report_threshold
        self.review_threshold = review_threshold
        self.max_hops = max_hops

    # -- entity assembly -----------------------------------------------------

    async def _enrich(self, rec: EntityRecord) -> None:
        hint = rec.addresses[0] if rec.addresses else rec.lookup_hint
        if rec.kind == "organization":
            ext = await self.provider.enrich_organization(rec.name, rec.tax_ids[0] if rec.tax_ids else None, hint)
        else:
            ext = await self.provider.enrich_person(rec.name, hint)
        if ext:
            rec.merge(ext)
            if "provider" not in rec.sources:
                rec.sources.append("provider")

    async def _resolve_kind(self, name: str, hint: Optional[str]) -> str:
        """Is an owner name a company or a person?  Ask the registry first ("Redstone
        Consulting" has no legal suffix but is a company), then fall back to the
        name heuristic."""
        if not _looks_like_person(name):
            return "organization"
        try:
            if await self.provider.enrich_organization(name, None, hint):
                return "organization"
            if await self.provider.enrich_person(name, hint):
                return "person"
        except Exception:
            pass
        return "person"

    async def _assemble(self, applicant: EntityRecord, key_personnel: List[EntityRecord],
                        counterparties: List[EntityRecord]) -> Tuple[Dict[str, EntityRecord], List[Edge]]:
        entities: Dict[str, EntityRecord] = {}
        structural: List[Edge] = []
        weights = self.weights

        async def add(rec: EntityRecord) -> EntityRecord:
            """Enrich first, then merge into an existing node unless the identifiers say
            this is a different person who happens to share the name.  Same-named
            people with disjoint addresses and phones become separate nodes
            (id suffixed #2, #3, ...) linked only by a soft same-name signal."""
            if rec.id not in entities or rec.kind == "person":
                await self._enrich(rec)
            base_id = rec.id
            n = 1
            while True:
                existing = entities.get(rec.id)
                if existing is None:
                    entities[rec.id] = rec
                    return rec
                if not identity_conflict(existing, rec) and not _unverifiable_merge(existing, rec):
                    existing.merge(rec)
                    return existing
                n += 1
                rec.id = f"{base_id}#{n}"

        async def expand(rec: EntityRecord, depth: int) -> None:
            """Pull officers/owners/spouse/household into the graph as nodes with structural edges."""
            if depth > 2:
                return
            if rec.kind == "organization":
                org_hint = rec.addresses[0] if rec.addresses else None
                for officer in rec.officers:
                    p = await add(EntityRecord(name=officer, kind="person", role="officer", lookup_hint=org_hint))
                    structural.append(Edge(p.id, rec.id, "officer_of", 0.98, structural=True,
                                           signals=[_sig("registry_officer", weights, None, f"{p.name} is a registered officer/director of {rec.name}")]))
                    await expand(p, depth + 1)
                for own in rec.owners:
                    kind = await self._resolve_kind(own.owner_name, org_hint)
                    o = await add(EntityRecord(name=own.owner_name, kind=kind, role="owner", lookup_hint=org_hint))
                    structural.append(Edge(o.id, rec.id, "owner_of", 0.98, structural=True,
                                           detail={"percent": own.percent},
                                           signals=[_sig("registry_ownership", weights, None, f"{o.name} owns {own.percent:.0f}% of {rec.name}")]))
                    await expand(o, depth + 1)
            else:
                home_hint = rec.addresses[0] if rec.addresses else None
                if rec.spouse:
                    s = await add(EntityRecord(name=rec.spouse, kind="person", role="related", lookup_hint=home_hint))
                    structural.append(Edge(rec.id, s.id, "spouse", 0.99, structural=True,
                                           signals=[_sig("marriage_record", weights, None, f"Marriage record links {rec.name} and {s.name}")]))
                    await expand(s, depth + 1)
                for member in rec.household_members:
                    mid = entity_id(member, "person")
                    if rec.spouse and entity_id(rec.spouse, "person") == mid:
                        continue
                    h = await add(EntityRecord(name=member, kind="person", role="related", lookup_hint=home_hint))
                    structural.append(Edge(rec.id, h.id, "household", 0.95, structural=True,
                                           signals=[_sig("household_record", weights, None, f"{rec.name} and {h.name} share a household")]))
                    await expand(h, depth + 1)

        applicant.role = "applicant"
        a = await add(applicant)
        await expand(a, 0)
        for kp in key_personnel:
            kp.role = "key_personnel"
            p = await add(kp)
            structural.append(Edge(p.id, a.id, "key_personnel_of", 0.99, structural=True,
                                   signals=[_sig("application_disclosure", weights, None, f"{p.name} is listed as key personnel on the application")]))
            await expand(p, 0)
        for cp in counterparties:
            c = await add(cp)
            await expand(c, 0)
        # Dedupe structural edges
        seen: Set[Tuple[str, str, str]] = set()
        unique: List[Edge] = []
        for e in structural:
            key = (min(e.source, e.target), max(e.source, e.target), e.kind)
            if key not in seen:
                seen.add(key)
                unique.append(e)
        return entities, unique

    # -- inference -----------------------------------------------------------

    def _infer_edges(self, entities: Dict[str, EntityRecord], structural: List[Edge],
                     application_date: Optional[date]) -> List[Edge]:
        """Pairwise attribute comparison.  When a pair already has a structural
        (registry / vital-records) edge, the inferred signals are folded into it
        as corroboration instead of creating a parallel edge, so the path
        description keeps the authoritative label ('owns 100% of')."""
        structural_by_pair: Dict[Tuple[str, str], List[Edge]] = {}
        for e in structural:
            structural_by_pair.setdefault((min(e.source, e.target), max(e.source, e.target)), []).append(e)
        # Officer/owner names already resolved to a specific node by a registry edge.  A
        # different person who merely shares that name must not pick up an inferred
        # "is officer of" link to the same company.
        resolved: Dict[Tuple[str, str], str] = {}
        for e in structural:
            if e.kind in {"officer_of", "owner_of"} and entities[e.source].kind == "person":
                resolved[(e.target, person_key(entities[e.source].name))] = e.source
            if e.kind in {"spouse", "household"}:
                # "X's spouse is named Sofia M." has been resolved to one Sofia node; another
                # Sofia must not inherit the marriage by name.
                resolved[(e.source, person_key(entities[e.target].name))] = e.target
                resolved[(e.target, person_key(entities[e.source].name))] = e.source
        name_claimed = {"is_officer_of", "is_owner_of", "officer_shares_surname", "is_employed_by"}
        kin_claimed = {"marriage_record", "household_record"}
        ids = list(entities)
        edges: List[Edge] = []
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a, b = entities[ids[i]], entities[ids[j]]
                signals = compare_entities(a, b, self.provider, application_date, self.weights)
                person, org = (a, b) if a.kind == "person" and b.kind == "organization" else \
                              (b, a) if b.kind == "person" and a.kind == "organization" else (None, None)
                if person is not None:
                    owner_node = resolved.get((org.id, person_key(person.name)))
                    if owner_node is not None and owner_node != person.id:
                        signals = [s for s in signals if s.kind not in name_claimed]
                elif a.kind == "person" and b.kind == "person":
                    kin_ab = resolved.get((a.id, person_key(b.name)))
                    kin_ba = resolved.get((b.id, person_key(a.name)))
                    if (kin_ab is not None and kin_ab != b.id) or (kin_ba is not None and kin_ba != a.id):
                        signals = [s for s in signals if s.kind not in kin_claimed]
                if not signals:
                    continue
                pair = (min(a.id, b.id), max(a.id, b.id))
                if pair in structural_by_pair:
                    redundant = {"officer_of": {"is_officer_of"}, "owner_of": {"is_owner_of"},
                                 "spouse": {"marriage_record"}, "household": {"household_record"}}
                    for se in structural_by_pair[pair]:
                        existing = {(s.kind, s.value) for s in se.signals}
                        skip = redundant.get(se.kind, set())
                        se.signals.extend(s for s in signals
                                          if (s.kind, s.value) not in existing and s.kind not in skip)
                        se.probability = max(se.probability, posterior_probability(se.llr_bits, self.prior))
                    continue
                bits = sum(s.llr_bits for s in signals)
                prob = posterior_probability(bits, self.prior)
                if prob < self.review_threshold:
                    continue
                edges.append(Edge(a.id, b.id, classify_signals(signals, a, b), prob, signals))
        return edges

    @staticmethod
    def _has_hard_evidence(edges: List[Edge]) -> bool:
        return any(e.structural or any(s.kind in HARD_SIGNALS for s in e.signals) for e in edges)

    # -- graph search ----------------------------------------------------------

    @staticmethod
    def _adjacency(edges: List[Edge]) -> Dict[str, List[Tuple[str, Edge]]]:
        adj: Dict[str, List[Tuple[str, Edge]]] = {}
        for e in edges:
            adj.setdefault(e.source, []).append((e.target, e))
            adj.setdefault(e.target, []).append((e.source, e))
        return adj

    def _best_path(self, adj: Dict[str, List[Tuple[str, Edge]]], sources: Set[str], target: str,
                   forbidden: Set[str]) -> Optional[Tuple[float, List[str], List[Edge]]]:
        """Max-probability path (product of edge probabilities) from any source to target,
        at most max_hops edges, avoiding `forbidden` intermediate nodes."""
        best: Optional[Tuple[float, List[str], List[Edge]]] = None
        heap: List[Tuple[float, int, str, List[str], List[Edge]]] = []
        for s in sources:
            heapq.heappush(heap, (0.0, 0, s, [s], []))
        visited: Dict[Tuple[str, int], float] = {}

        def rank(prob: float, path_edges: List[Edge]) -> Tuple[float, int, int]:
            # Probabilities within the same tenth are treated as tied.  Ties go to the
            # path with the fewest inferred hops (each inferred edge is a point an
            # investigator must defend; registry / vital records are not), so
            # "married to X, who owns Y" beats "shares a phone with Y"; then to the
            # shorter path.
            inferred = sum(not e.structural for e in path_edges)
            return (round(prob, 1), -inferred, -len(path_edges))

        while heap:
            cost, hops, node, path, path_edges = heapq.heappop(heap)
            if node == target:
                prob = math.exp(-cost)
                if best is None or rank(prob, path_edges) > rank(best[0], best[2]):
                    best = (prob, path, path_edges)
                continue
            if hops >= self.max_hops:
                continue
            for nxt, edge in adj.get(node, []):
                # Never route through another start node: a path that passes through a
                # source is dominated by the path that simply starts there.
                if nxt in path or nxt in sources or (nxt in forbidden and nxt != target):
                    continue
                ncost = cost - math.log(max(edge.probability, 1e-9))
                key = (nxt, hops + 1)
                if key in visited and visited[key] <= ncost:
                    continue
                visited[key] = ncost
                heapq.heappush(heap, (ncost, hops + 1, nxt, path + [nxt], path_edges + [edge]))
        return best

    @staticmethod
    def _indirect_ownership(structural: List[Edge], sources: Set[str], target: str,
                            entities: Dict[str, EntityRecord]) -> float:
        """Sum over ownership chains of the product of percentages, from any applicant-side
        person/org to the target."""
        owners_of: Dict[str, List[Tuple[str, float]]] = {}
        for e in structural:
            if e.kind == "owner_of":
                owners_of.setdefault(e.target, []).append((e.source, e.detail.get("percent", 0.0) / 100.0))
        memo: Dict[str, float] = {}

        def share(node: str, depth: int) -> float:
            if node in sources:
                return 1.0
            if depth > 4 or node not in owners_of:
                return 0.0
            if node in memo:
                return memo[node]
            total = sum(pct * share(owner, depth + 1) for owner, pct in owners_of[node])
            memo[node] = total
            return total

        if target in sources:
            return 0.0
        return round(min(share(target, 0) * 100.0, 100.0), 1)

    # -- classification --------------------------------------------------------

    @staticmethod
    def _describe_path(path: List[str], edges: List[Edge], entities: Dict[str, EntityRecord]) -> str:
        parts = [entities[path[0]].name]
        labels = {
            "spouse": "is married to", "household": "shares a household with", "cohabitant": "lives with",
            "officer_of": "is an officer of", "owner_of": "owns", "key_personnel_of": "is key personnel on",
            "same_person": "is the same person as", "same_entity": "is the same entity as",
            "ownership_interest": "holds ownership in", "employed_by": "is employed by",
            "common_control": "is under common control with", "operational_control": "shares operational control with",
            "shell_cluster": "forms a shell cluster with", "co_located": "is co-located with",
            "same_building": "is in the same building as", "possible_family": "may be related to",
            "possible_affiliate": "may be affiliated with", "weak_association": "is weakly associated with",
        }
        for node, edge in zip(path[1:], edges):
            label = labels.get(edge.kind, edge.kind.replace("_", " "))
            if edge.kind == "owner_of" and edge.detail.get("percent") is not None:
                label = f"owns {edge.detail['percent']:.0f}% of"
            parts.append(f"{label} {entities[node].name}")
        return " → ".join(parts)

    @staticmethod
    def _path_type(edges: List[Edge], ownership_pct: float) -> Tuple[str, bool, bool]:
        """Returns (relationship_type, self_dealing, immediate_family)."""
        kinds = [e.kind for e in edges]
        personal = any(k in {"spouse", "household", "cohabitant"} for k in kinds)
        structural_interest = any(k in {"owner_of", "officer_of", "ownership_interest", "same_entity", "same_person"} for k in kinds)
        if len(edges) == 1:
            k = kinds[0]
            if k in {"ownership_interest", "owner_of", "officer_of", "same_entity", "same_person", "employed_by"}:
                return k, k != "employed_by", False
            if k in {"spouse", "household", "cohabitant"}:
                return k, False, k != "cohabitant"
            return k, k in {"common_control"} and ownership_pct > 0, False
        if "spouse" in kinds and structural_interest:
            return "spouse_controlled_entity", True, True
        if personal and structural_interest:
            return "family_controlled_entity", True, True
        if ownership_pct > 0:
            return "indirect_ownership", True, False
        if structural_interest:
            return "indirect_control", True, False
        if any(k in {"common_control", "operational_control", "shell_cluster"} for k in kinds):
            return "affiliated_network", False, False
        if personal:
            return "family_association", False, True
        return "indirect_association", False, False

    @staticmethod
    def _uniform_guidance(rel_type: str, self_dealing: bool, immediate_family: bool,
                          counterparty_role: str, ownership_pct: float, band: str) -> List[str]:
        cites: List[str] = []
        if band != "confirmed":
            return [f"2 CFR 200.112: potential conflict should be disclosed to the awarding agency; verification recommended ({rel_type.replace('_', ' ')})"]
        if immediate_family:
            cites.append(f"2 CFR 200.318(c)(1): {counterparty_role} is controlled by or tied to an immediate family member of applicant personnel")
        if self_dealing:
            pct = f" ({ownership_pct:.0f}% indirect ownership)" if ownership_pct else ""
            cites.append(f"2 CFR 200.318(c)(1): applicant personnel hold a financial interest in the {counterparty_role}{pct}")
        if rel_type in {"common_control", "affiliated_network", "shell_cluster", "indirect_control", "same_entity",
                        "operational_control"}:
            cites.append(f"2 CFR 200.318(c)(2): organizational conflict; {counterparty_role} is a parent, affiliate or subsidiary of the applicant")
        if rel_type in {"shell_cluster", "operational_control"}:
            cites.append("2 CFR 200.319: lack of full and open competition; counterparties are not independent")
        if not cites:
            cites.append(f"2 CFR 200.112: undisclosed related-party relationship ({rel_type.replace('_', ' ')}) requires written disclosure")
        return cites

    # -- public API ----------------------------------------------------------

    async def analyze(self, applicant: EntityRecord, counterparties: List[EntityRecord],
                      key_personnel: Optional[List[EntityRecord]] = None,
                      application_date: Optional[Any] = None) -> RelationshipAnalysis:
        key_personnel = key_personnel or []
        app_date = _parse_date(application_date)
        counterparty_ids = {entity_id(c.name, c.kind) for c in counterparties}

        entities, structural = await self._assemble(applicant, key_personnel, counterparties)
        inferred = self._infer_edges(entities, structural, app_date)
        all_edges = structural + inferred
        adj = self._adjacency(all_edges)

        # Applicant side = applicant + key personnel + applicant's officers/owners
        applicant_side: Set[str] = {applicant.id} | {kp.id for kp in key_personnel}
        for e in structural:
            if e.kind in {"officer_of", "owner_of", "key_personnel_of"} and e.target == applicant.id:
                applicant_side.add(e.source)

        findings: List[RelationshipFinding] = []
        review: List[RelationshipFinding] = []
        for cid in counterparty_ids:
            if cid not in entities or cid in applicant_side:
                continue
            other_counterparties = counterparty_ids - {cid}
            best = self._best_path(adj, applicant_side, cid, forbidden=other_counterparties)
            if not best:
                continue
            prob, path, path_edges = best
            if prob < self.review_threshold:
                continue
            own_pct = self._indirect_ownership(structural, applicant_side, cid, entities)
            rel_type, self_dealing, immediate_family = self._path_type(path_edges, own_pct)
            # Soft evidence alone (surnames, registered agents, timing) can never confirm;
            # every edge on the path must carry at least one hard identifier or registry record.
            all_hard = all(e.structural or any(s.kind in HARD_SIGNALS for s in e.signals) for e in path_edges)
            band = "confirmed" if prob >= self.report_threshold and all_hard else "review"
            counterparty = entities[cid]
            evidence: List[str] = []
            signals: List[Dict[str, Any]] = []
            for e in path_edges:
                for line in e.evidence():
                    if line not in evidence:
                        evidence.append(line)
                signals.extend(s.to_dict() for s in e.signals)
            finding = RelationshipFinding(
                counterparty=counterparty.name,
                counterparty_role=counterparty.role,
                relationship_type=rel_type,
                probability=round(prob, 4),
                evidence_bits=round(sum(e.llr_bits for e in path_edges), 2),
                direct=len(path_edges) == 1,
                path=[entities[n].name for n in path],
                path_description=self._describe_path(path, path_edges, entities),
                evidence=evidence,
                signals=signals,
                indirect_ownership_percent=own_pct,
                uniform_guidance=self._uniform_guidance(rel_type, self_dealing, immediate_family,
                                                        counterparty.role, own_pct, band),
                self_dealing=self_dealing and band == "confirmed",
                immediate_family=immediate_family and band == "confirmed",
                band=band,
            )
            (findings if band == "confirmed" else review).append(finding)

        findings.sort(key=lambda f: -f.probability)
        review.sort(key=lambda f: -f.probability)
        # Keep the exported graph legible: structural edges, inferred edges with hard
        # evidence, and any soft edge that actually sits on a reported path.
        path_pairs: Set[Tuple[str, str]] = set()
        for f in findings + review:
            ids_on_path = [entity_id(n, "person") for n in f.path] + [entity_id(n, "organization") for n in f.path]
            for x in ids_on_path:
                for y in ids_on_path:
                    path_pairs.add((x, y))
        export_edges = [e for e in all_edges
                        if e.structural or any(s.kind in HARD_SIGNALS for s in e.signals)
                        or (e.source, e.target) in path_pairs]
        graph = self._export_graph(entities, export_edges, applicant_side, counterparty_ids, findings + review)
        return RelationshipAnalysis(findings=findings, review_recommended=review, graph=graph,
                                    entity_count=len(entities), edge_count=len(all_edges))

    # -- export ----------------------------------------------------------------

    @staticmethod
    def _export_graph(entities: Dict[str, EntityRecord], edges: List[Edge], applicant_side: Set[str],
                      counterparty_ids: Set[str], findings: List[RelationshipFinding]) -> Dict[str, Any]:
        flagged = {entity_id(f.counterparty, "organization") for f in findings} | \
                  {entity_id(f.counterparty, "person") for f in findings}
        on_path: Set[str] = set()
        for f in findings:
            for name in f.path:
                on_path.add(entity_id(name, "person"))
                on_path.add(entity_id(name, "organization"))
        nodes = []
        for eid, rec in entities.items():
            side = "applicant" if eid in applicant_side else "counterparty" if eid in counterparty_ids else "intermediary"
            nodes.append({
                "id": eid, "label": rec.name, "kind": rec.kind, "role": rec.role, "side": side,
                "flagged": eid in flagged, "on_path": eid in on_path,
            })
        edge_list = []
        for e in edges:
            edge_list.append({
                "source": e.source, "target": e.target, "kind": e.kind,
                "confidence": round(e.probability, 3), "structural": e.structural,
                "label": e.kind.replace("_", " ") + (f" {e.detail['percent']:.0f}%" if e.detail.get("percent") else ""),
                "evidence": e.evidence(),
            })
        # Shared-identifier nodes make the hidden link visible: A —lives at→ addr ←registered at— B
        attr_nodes: Dict[str, Dict[str, Any]] = {}
        attr_edges: List[Dict[str, Any]] = []
        for e in edges:
            if e.structural:
                continue
            for s in e.signals:
                if s.kind in {"same_residential_address", "same_address", "same_phone", "same_email",
                              "same_bank_account", "same_tax_id", "same_private_domain", "same_device", "same_ip_address"} and s.value:
                    aid = f"attr:{s.kind}:{s.value}"
                    attr_nodes.setdefault(aid, {"id": aid, "label": s.value, "kind": "identifier",
                                                "identifier_type": s.kind.replace("same_", ""), "role": "shared_identifier",
                                                "side": "identifier", "flagged": False, "on_path": False})
                    for endpoint in (e.source, e.target):
                        attr_edges.append({"source": endpoint, "target": aid, "kind": "has_identifier",
                                           "confidence": 1.0, "structural": False, "label": "", "evidence": []})
        seen_attr: Set[Tuple[str, str]] = set()
        dedup_attr_edges = []
        for ae in attr_edges:
            k = (ae["source"], ae["target"])
            if k not in seen_attr:
                seen_attr.add(k)
                dedup_attr_edges.append(ae)
        return {"nodes": nodes + list(attr_nodes.values()), "edges": edge_list + dedup_attr_edges}


_ORG_WORDS = {
    "holdings", "trust", "partners", "group", "fund", "capital", "consulting", "services", "service", "solutions",
    "laboratories", "laboratory", "labs", "technologies", "technology", "systems", "data", "analytics", "research",
    "institute", "associates", "enterprises", "international", "global", "logistics", "construction", "engineering",
    "environmental", "development", "housing", "health", "education", "workforce", "foundation", "ventures",
    "industries", "management", "properties", "realty", "investments", "medical", "clinic", "center", "centre",
    "university", "college", "school", "church", "ministries", "bank", "insurance", "farms", "ranch", "company",
}


def _unverifiable_merge(existing: EntityRecord, incoming: EntityRecord) -> bool:
    """True when one same-named person record has no identifiers at all and the other
    was found through a different lookup hint.  Merging would assert, on the name
    alone, that an unresolved applicant-side person is the individual found via a
    counterparty's household or officer list.  Keep them apart; the soft
    `same_name_unverified` signal records the possibility."""
    if existing.kind != "person" or incoming.kind != "person":
        return False
    if has_identifiers(existing) == has_identifiers(incoming):
        return False

    def hint_base(rec: EntityRecord) -> Optional[str]:
        src = rec.addresses[0] if rec.addresses else rec.lookup_hint
        c = canonical_address(src) if src else None
        return c.base if c else None

    return hint_base(existing) != hint_base(incoming)


def _looks_like_person(name: str) -> bool:
    tokens = _strip_punct(name.replace(".", "")).split()
    if any(t in _ORG_SUFFIXES or t in _ORG_WORDS for t in tokens):
        return False
    if any(t.isdigit() for t in tokens) or "&" in name:
        return False
    return 2 <= len(tokens) <= 4


def entity_from_party(party: Dict[str, Any], default_role: str) -> EntityRecord:
    """Build an EntityRecord from a loosely-typed application party dict."""
    addresses = [a for a in [party.get("address")] + list(party.get("addresses", [])) if a]
    address_types = dict(party.get("address_types", {}))
    if party.get("address_type") and party.get("address"):
        address_types[party["address"]] = party["address_type"]
    bank_hashes = list(party.get("bank_account_hashes", []))
    if party.get("bank_routing") and party.get("bank_account"):
        bank_hashes.append(hash_bank_account(party["bank_routing"], party["bank_account"]))
    owners = [Ownership(o["name"], float(o.get("percent", 0))) if isinstance(o, dict) else Ownership(str(o), 0.0)
              for o in party.get("owners", [])]
    kind = party.get("kind") or ("person" if party.get("is_person") else "organization")
    return EntityRecord(
        name=party.get("name", "").strip(),
        kind=kind,
        role=party.get("role_type") or default_role,
        addresses=addresses,
        address_types=address_types,
        phones=[p for p in [party.get("phone")] + list(party.get("phones", [])) if p],
        emails=[e for e in [party.get("email")] + list(party.get("emails", [])) if e],
        websites=[w for w in [party.get("website")] + list(party.get("websites", [])) if w],
        tax_ids=[t for t in [party.get("tax_id"), party.get("ein")] + list(party.get("tax_ids", [])) if t],
        bank_account_hashes=bank_hashes,
        ip_addresses=list(party.get("ip_addresses", [])),
        device_ids=list(party.get("device_ids", [])),
        registered_agent=party.get("registered_agent"),
        incorporation_date=party.get("incorporation_date"),
        officers=list(party.get("officers", [])),
        owners=owners,
        spouse=party.get("spouse"),
        household_members=list(party.get("household_members", [])),
        employer=party.get("employer"),
        sources=["application"],
    )
