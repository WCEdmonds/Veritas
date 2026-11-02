"""
Synthetic ground-truth benchmark for the relationship engine.

Generates a population of people, households and companies, builds grant cases
from it, plants relationship patterns with known answers, adds the noise that
defeats naive matching, runs the engine, and scores it.

    cd backend
    python -m benchmarks.synthetic --cases 300 --seed 7
    python -m benchmarks.synthetic --cases 300 --weights calibrated_weights.json --json report.json
    python -m benchmarks.synthetic --no-vital-records          # no marriage/household feed available
    python -m benchmarks.synthetic --coverage 0.6              # provider finds only 60% of entities

Patterns planted per case (positives must be found, negatives must not):

  POSITIVE  spouse_contractor   PI's spouse owns the contractor (home-based, maybe different surname)
  POSITIVE  nickname_disguise   spouse_contractor, but the spouse is listed as a nickname / initial
  POSITIVE  holding_chain       PI owns X% of a holding company that owns Y% of the vendor
  POSITIVE  straw_owner         An adult household member of the PI is the paper owner
  POSITIVE  self_officer        PI is a registered officer of the counterparty
  POSITIVE  home_shell          Counterparty registered at the PI's home with the PI's cell phone, formed recently
  NEGATIVE  surname_coincidence Counterparty officer shares the PI's surname, nothing else
  NEGATIVE  same_building       Counterparty is another tenant in the applicant's building
  NEGATIVE  same_agent          Counterparty shares a registered agent with the applicant
  NEGATIVE  clean               Random unrelated company

Metrics: precision / recall / F1 of the confirmed band, recall by positive
pattern, false-positive rate by negative pattern, review-band usage, type
accuracy (family vs financial interest, indirect ownership %), Brier score and
a reliability table for the probabilities.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.agent.relationships import (
    DEFAULT_WEIGHTS,
    EntityRecord,
    Ownership,
    RelationshipEngine,
    Weights,
    canonical_address,
    canonical_org_name,
    load_weights,
    person_key,
)

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

GIVEN = {
    "f": ["jennifer", "patricia", "elizabeth", "katherine", "margaret", "susan", "rebecca", "deborah", "cynthia",
          "amanda", "sandra", "christina", "jessica", "stephanie", "victoria", "eleanor", "allison", "abigail",
          "maria", "linda", "karen", "nancy", "lisa", "angela", "melissa", "michelle", "laura", "sarah", "emily",
          "priya", "aisha", "mei", "fatima", "yuki", "ana", "sofia", "ingrid", "nadia", "olga"],
    "m": ["william", "robert", "richard", "james", "john", "michael", "daniel", "david", "thomas", "christopher",
          "matthew", "anthony", "steven", "joseph", "edward", "charles", "benjamin", "samuel", "alexander", "andrew",
          "nicholas", "nathan", "patrick", "jonathan", "marcus", "kevin", "brian", "george", "mark", "paul",
          "raj", "omar", "wei", "ahmed", "hiroshi", "carlos", "luis", "sven", "dmitri", "kwame"],
}
NICK = {"william": ["bill", "will"], "robert": ["bob", "rob"], "richard": ["rick", "dick"], "james": ["jim"],
        "john": ["jack"], "michael": ["mike"], "daniel": ["dan", "danny"], "david": ["dave"], "thomas": ["tom"],
        "christopher": ["chris"], "matthew": ["matt"], "anthony": ["tony"], "steven": ["steve"], "joseph": ["joe"],
        "edward": ["ed", "ted"], "charles": ["chuck", "charlie"], "benjamin": ["ben"], "samuel": ["sam"],
        "andrew": ["andy", "drew"], "nicholas": ["nick"], "patrick": ["pat"], "jennifer": ["jen", "jenny"],
        "patricia": ["pat", "trish"], "elizabeth": ["liz", "beth"], "katherine": ["kate", "katie"],
        "margaret": ["peggy", "maggie"], "susan": ["sue"], "rebecca": ["becky"], "deborah": ["deb", "debbie"],
        "cynthia": ["cindy"], "amanda": ["mandy"], "christina": ["tina"], "jessica": ["jess"],
        "stephanie": ["steph"], "victoria": ["vicky", "tori"], "eleanor": ["ellie"], "allison": ["ally"],
        "abigail": ["abby"]}

# Surname list with a Zipf-like frequency so a few names are very common and most are rare,
# which is what real populations look like.  The first entries match the engine's frequency table.
SURNAMES = ["smith", "johnson", "williams", "brown", "jones", "garcia", "miller", "davis", "rodriguez", "martinez",
            "hernandez", "lopez", "gonzalez", "wilson", "anderson", "thomas", "taylor", "moore", "jackson", "martin",
            "lee", "perez", "thompson", "white", "harris", "sanchez", "clark", "ramirez", "lewis", "robinson",
            "walker", "young", "allen", "king", "wright", "scott", "torres", "nguyen", "hill", "flores",
            "green", "adams", "nelson", "baker", "hall", "rivera", "campbell", "mitchell", "carter", "roberts",
            "hale", "oyelaran", "raman", "whitcomb", "delacroix", "okafor", "lindqvist", "farrukh", "takahashi",
            "brennan", "castellano", "duvall", "eisenberg", "fairbanks", "galloway", "hargrove", "ibarra", "jernigan",
            "kowalski", "lachance", "mcallister", "nakamura", "oduya", "pennington", "quintero", "rasmussen",
            "schofield", "thibodeaux", "underwood", "vanderberg", "wexler", "yamamoto", "zielinski", "abernathy",
            "blackwood", "carrington", "dunmore", "ellsworth", "fontaine", "greenlee", "holloway", "ingersoll",
            "jaworski", "kettering", "lockhart", "maddox", "northcutt", "overstreet", "pemberton", "radcliffe",
            "stanfield", "tolliver", "upshaw", "vandiver", "westbrook", "yarbrough", "ziegler", "ashcroft",
            "bainbridge", "crenshaw", "dellinger", "eastwood", "fenwick", "gaskins", "hathaway", "isherwood",
            "kirkpatrick", "lindgren", "merriweather", "nightingale", "ostrowski", "prendergast", "rutherford",
            "satterfield", "thorncroft", "vasquez", "whitlock", "yeager", "zimmerman"]

STREETS = ["Juniper", "Research", "Canyon", "Pine", "Elm", "Industrial", "Maple", "Cedar", "Oak", "Willow", "Aspen",
           "Mesa", "Ridge", "Summit", "Valley", "Lake", "River", "Prairie", "Union", "Market", "Main", "College",
           "Broadway", "Washington", "Lincoln", "Jefferson", "Franklin", "Highland", "Sunset", "Meadow", "Harbor",
           "Foothills", "Boulder", "Arapahoe", "Colfax", "Speer", "Baseline", "Table Mesa", "Iris", "Folsom"]
SUFFIX = ["St", "Ave", "Rd", "Dr", "Blvd", "Ln", "Ct", "Pl", "Way", "Pkwy"]
CITIES = [("Boulder", "CO", "8030"), ("Denver", "CO", "8020"), ("Longmont", "CO", "8050"), ("Fort Collins", "CO", "8052"),
          ("Golden", "CO", "8040"), ("Aurora", "CO", "8001"), ("Lakewood", "CO", "8022"), ("Santa Fe", "NM", "8750"),
          ("Albuquerque", "NM", "8710"), ("Cheyenne", "WY", "8200"), ("Omaha", "NE", "6810"), ("Austin", "TX", "7870")]
ORG_A = ["Northstar", "Meridian", "Summit", "Front Range", "Blue Mesa", "Rio Grande", "Harbor Light", "Pinnacle", "Vertex",
         "Cascade", "Granite", "Horizon", "Keystone", "Lighthouse", "Monarch", "Nimbus", "Obsidian", "Pioneer", "Quantum",
         "Redstone", "Silverline", "Timberline", "Upland", "Vista", "Westward", "Zenith", "Aspen Grove", "Clearwater",
         "Evergreen", "Foxglove", "Ironwood", "Juniper Ridge", "Larkspur", "Mesa Verde", "Oakhaven", "Prairie Wind"]
ORG_B = ["Analytics", "Research", "Consulting", "Field Services", "Statistical", "Data Services", "Community Development",
         "Engineering", "Logistics", "Environmental", "Laboratories", "Technologies", "Construction", "Health Partners",
         "Education", "Housing", "Workforce", "Systems", "Solutions", "Associates", "Group", "Institute", "Partners"]
ORG_SUFFIX = ["LLC", "Inc", "Corp", "L.L.C.", "Inc.", "Co", "LLP", ""]
# Big commercial agents first, then a long tail of attorneys and accountants acting as agents.
# Sampled with a flat Zipf so the collision rate lands near what the Colorado registry shows (~0.3%).
AGENTS = ["Registered Agents Inc", "CT Corporation System", "CSC", "Northwest Registered Agent", "InCorp Services",
          "Harbor Compliance", "LegalZoom", "ZenBusiness"] + \
         [f"{s.title()} Law Office" for s in SURNAMES[50:]] + \
         [f"{g.title()} {s.title()} CPA" for g in GIVEN["m"][:12] for s in SURNAMES[60:90]]
PUBLIC_DOMAINS = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com"]


def zipf_choice(rng: random.Random, items: List[str], s: float = 1.0) -> str:
    weights = [1.0 / ((i + 1) ** s) for i in range(len(items))]
    return rng.choices(items, weights=weights, k=1)[0]


# ---------------------------------------------------------------------------
# World model
# ---------------------------------------------------------------------------

@dataclass
class Person:
    first: str
    last: str
    sex: str
    birth_year: int
    home: str
    phone: str
    email: str
    spouse: Optional[str] = None          # person id
    household: List[str] = field(default_factory=list)
    id: str = ""

    @property
    def name(self) -> str:
        return f"{self.first.title()} {self.last.title()}"


@dataclass
class Company:
    name: str
    address: str
    address_type: str                     # residential | commercial | registered_agent
    phone: str
    domain: str
    agent: str
    formed: date
    officers: List[str] = field(default_factory=list)      # person ids
    owners: List[Tuple[str, float]] = field(default_factory=list)   # (person or company id, pct)
    tax_id: str = ""
    id: str = ""


class World:
    def __init__(self, rng: random.Random, n_households: int = 400, n_companies: int = 600) -> None:
        self.rng = rng
        self.people: Dict[str, Person] = {}
        self.companies: Dict[str, Company] = {}
        self._org_keys: set = set()
        self.by_org_key: Dict[str, Company] = {}      # canonical org name -> company (kept current as cases plant companies)
        self.by_person_key: Dict[str, List[Person]] = {}    # nickname-resolved "first last" -> people with that name
        self._emails: set = set()
        self.buildings: List[str] = [self._street_address(commercial=True) for _ in range(400)]
        self.agent_addresses = {a: self._street_address(commercial=True) for a in AGENTS[:8]}
        for _ in range(n_households):
            self._make_household()
        for _ in range(n_companies):
            self._make_company()

    # -- primitives ---------------------------------------------------------
    def _street_address(self, commercial: bool = False, unit: Optional[str] = None) -> str:
        city, st, zip_prefix = self.rng.choice(CITIES)
        num = self.rng.randint(100, 9999)
        street = f"{self.rng.choice(STREETS)} {self.rng.choice(SUFFIX)}"
        base = f"{num} {street}, {city}, {st} {zip_prefix}{self.rng.randint(0, 9)}"
        if commercial and unit:
            return f"{num} {street} Suite {unit}, {city}, {st} {zip_prefix}{self.rng.randint(0, 9)}"
        return base

    def _phone(self) -> str:
        return f"{self.rng.choice(['303', '720', '970', '505', '307', '402', '512'])}-555-{self.rng.randint(0, 9999):04d}"

    def _person(self, last: str, sex: str, birth_year: int, home: str) -> Person:
        first = self.rng.choice(GIVEN[sex])
        pid = f"p{len(self.people)}"
        domain = self.rng.choice(PUBLIC_DOMAINS)
        email = f"{first[0]}{last}@{domain}"
        if email in self._emails:                      # real mailboxes are unique per person
            email = f"{first[0]}{last}{self.rng.randint(10, 999)}@{domain}"
        self._emails.add(email)
        p = Person(first, last, sex, birth_year, home, self._phone(), email, id=pid)
        self.people[pid] = p
        self.by_person_key.setdefault(person_key(p.name), []).append(p)
        return p

    def _make_household(self) -> None:
        last = zipf_choice(self.rng, SURNAMES, 0.6)
        home = self._street_address()
        a = self._person(last, "m", self.rng.randint(1950, 1990), home)
        members = [a]
        if self.rng.random() < 0.7:  # married
            spouse_last = last if self.rng.random() < 0.75 else zipf_choice(self.rng, SURNAMES, 0.6)
            b = self._person(spouse_last, "f", a.birth_year + self.rng.randint(-5, 5), home)
            a.spouse, b.spouse = b.id, a.id
            members.append(b)
            if self.rng.random() < 0.4:  # adult child still at home
                c = self._person(last, self.rng.choice("mf"), a.birth_year + self.rng.randint(22, 32), home)
                members.append(c)
        for m in members:
            m.household = [x.id for x in members if x.id != m.id]

    def _org_name(self) -> str:
        for _ in range(1000):
            name = f"{self.rng.choice(ORG_A)} {self.rng.choice(ORG_B)} {self.rng.choice(ORG_SUFFIX)}".strip()
            key = canonical_org_name(name)
            if key not in self._org_keys:
                self._org_keys.add(key)
                return name
        # Vocabulary exhausted: disambiguate with a numeral, still checking the canonical key.
        n = len(self.companies)
        while True:
            name = f"{self.rng.choice(ORG_A)} {self.rng.choice(ORG_B)} {n} {self.rng.choice(ORG_SUFFIX)}".strip()
            key = canonical_org_name(name)
            if key not in self._org_keys:
                self._org_keys.add(key)
                return name
            n += 1

    def _make_company(self, officers: Optional[List[str]] = None, address: Optional[str] = None,
                      address_type: Optional[str] = None, phone: Optional[str] = None, agent: Optional[str] = None,
                      formed: Optional[date] = None, owners: Optional[List[Tuple[str, float]]] = None) -> Company:
        if officers is None:
            officers = [self.rng.choice(list(self.people))]
        if address is None:
            r = self.rng.random()
            if r < 0.25:   # home-based business
                address, address_type = self.people[officers[0]].home, "residential"
            elif r < 0.85 or (agent and agent not in self.agent_addresses):
                address, address_type = f"{self.rng.choice(self.buildings).replace(',', f' Suite {self.rng.randint(100, 900)},', 1)}", "commercial"
            else:
                agent = agent or self.rng.choice(AGENTS[:8])
                address, address_type = self.agent_addresses[agent], "registered_agent"
        agent = agent or zipf_choice(self.rng, AGENTS, 0.8)
        formed = formed or date(2024, 1, 1) - timedelta(days=self.rng.randint(0, 365 * 20))
        name = self._org_name()
        cid = f"c{len(self.companies)}"
        slug = canonical_org_name(name).replace(" ", "")[:18]
        if any(c.domain == f"{slug}.com" for c in self.companies.values()):
            slug = f"{slug}{len(self.companies)}"          # web domains are unique in the real world
        c = Company(name, address, address_type or "commercial",
                    phone or (self.people[officers[0]].phone if self.rng.random() < 0.3 else self._phone()),
                    f"{slug}.com", agent, formed, officers,
                    owners if owners is not None else [(officers[0], 100.0)],
                    tax_id=f"{self.rng.randint(10, 99)}-{self.rng.randint(1000000, 9999999)}", id=cid)
        self.companies[cid] = c
        self.by_org_key[canonical_org_name(name)] = c
        return c

    # -- lookups used by the provider ------------------------------------------
    def person_record(self, p: Person, vital_records: bool) -> EntityRecord:
        return EntityRecord(
            name=p.name, kind="person", role="related", addresses=[p.home], address_types={p.home: "residential"},
            phones=[p.phone], emails=[p.email],
            spouse=self.people[p.spouse].name if (vital_records and p.spouse) else None,
            household_members=[self.people[h].name for h in p.household] if vital_records else [],
            sources=["synthetic_provider"],
        )

    def company_record(self, c: Company) -> EntityRecord:
        owners = []
        for oid, pct in c.owners:
            owners.append(Ownership(self.people[oid].name if oid in self.people else self.companies[oid].name, pct))
        return EntityRecord(
            name=c.name, kind="organization", role="related", addresses=[c.address],
            address_types={c.address: c.address_type}, phones=[c.phone], websites=[c.domain], tax_ids=[c.tax_id],
            registered_agent=c.agent, incorporation_date=c.formed.isoformat(),
            officers=[self.people[o].name for o in c.officers], owners=owners, sources=["synthetic_registry"],
        )


class SyntheticProvider:
    """RelationshipDataProvider over the synthetic world with configurable coverage."""

    def __init__(self, world: World, rng: random.Random, coverage: float = 1.0, vital_records: bool = True) -> None:
        self.world = world
        self.rng = rng
        self.coverage = coverage
        self.vital_records = vital_records
        self._agent_bases = {canonical_address(a).base for a in world.agent_addresses.values()}
        self._missing: Dict[str, bool] = {}

    def _covered(self, key: str) -> bool:
        if key not in self._missing:
            self._missing[key] = self.rng.random() < self.coverage
        return self._missing[key]

    async def enrich_organization(self, name, tax_id=None, address=None):
        c = self.world.by_org_key.get(canonical_org_name(name))
        return self.world.company_record(c) if c and self._covered(c.id) else None

    async def enrich_person(self, name, address=None):
        """Like a careful aggregator: several people can share a name.  The address hint
        picks among them; if it does not settle the question the lookup returns None
        instead of guessing (see RelationshipDataProvider.enrich_person)."""
        candidates = self.world.by_person_key.get(person_key(name), [])
        if not candidates:
            return None
        if len(candidates) == 1:
            p = candidates[0]
        else:
            hint = canonical_address(address) if address else None
            # A real registry attaches each officer row to its company, so an officer
            # looked up from a company's address resolves to the person on that filing.
            matches = [c for c in candidates
                       if hint and (h := canonical_address(c.home)) and h.base == hint.base]
            if not matches and hint:
                for comp in self.world.companies.values():
                    ca = canonical_address(comp.address)
                    if ca and ca.base == hint.base:
                        matches.extend(self.world.people[o] for o in comp.officers if self.world.people[o] in candidates)
                matches = list({m.id: m for m in matches}.values())
            if len(matches) != 1:
                return None
            p = matches[0]
        return self.world.person_record(p, self.vital_records) if self._covered(p.id) else None

    def is_registered_agent_address(self, canonical_base_address: str) -> bool:
        return canonical_base_address in self._agent_bases


# ---------------------------------------------------------------------------
# Noise: how the application would actually spell things
# ---------------------------------------------------------------------------

def noisy_person_name(rng: random.Random, p: Person) -> str:
    first = p.first
    r = rng.random()
    if r < 0.25 and first in NICK:
        first = rng.choice(NICK[first])
    elif r < 0.35:
        first = first[0] + "."
    name = f"{first.title()} {p.last.title()}"
    if rng.random() < 0.3:
        name = f"{rng.choice(['Dr.', 'Mr.', 'Ms.', 'Prof.'])} {name}"
    if rng.random() < 0.15:
        name = f"{name}, {rng.choice(['PhD', 'Jr.', 'MBA'])}"
    return name


def noisy_address(rng: random.Random, addr: str) -> str:
    out = addr
    swaps = [(" St,", " Street,"), (" Ave,", " Avenue,"), (" Rd,", " Road,"), (" Dr,", " Drive,"), (" Blvd,", " Boulevard,"),
             (" Suite ", " Ste "), (" Suite ", " #"), (", CO ", " CO "), (", NM ", " NM ")]
    for a, b in swaps:
        if a in out and rng.random() < 0.5:
            out = out.replace(a, b, 1)
    if rng.random() < 0.3:
        out = out + f"-{rng.randint(1000, 9999)}"   # ZIP+4
    if rng.random() < 0.2:
        out = out.upper()
    return out


def noisy_org_name(rng: random.Random, name: str) -> str:
    r = rng.random()
    if r < 0.2 and name.endswith("LLC"):
        return name[:-3] + "L.L.C."
    if r < 0.3 and name.endswith("Inc"):
        return name + "."
    if r < 0.4:
        return "The " + name
    return name


# ---------------------------------------------------------------------------
# Case construction with planted truth
# ---------------------------------------------------------------------------

LAST_INPUTS: Optional[Tuple[EntityRecord, List[EntityRecord], List[EntityRecord]]] = None

POSITIVE = ["spouse_contractor", "nickname_disguise", "holding_chain", "straw_owner", "self_officer", "home_shell"]
NEGATIVE = ["surname_coincidence", "same_building", "same_agent", "clean"]


@dataclass
class Planted:
    company: Company
    pattern: str
    related: bool
    expect_family: bool = False
    expect_financial: bool = False
    expect_ownership_pct: Optional[float] = None
    presented_name: str = ""


@dataclass
class Case:
    applicant: Company
    pi: Person
    counterparties: List[Planted]
    application_date: date


def build_case(world: World, rng: random.Random) -> Case:
    # Applicant: a commercial-address company whose first officer is the PI and has a spouse.
    candidates = [c for c in world.companies.values()
                  if c.address_type == "commercial" and world.people[c.officers[0]].spouse]
    applicant = rng.choice(candidates)
    pi = world.people[applicant.officers[0]]
    spouse = world.people[pi.spouse]
    app_date = date(2025, 10, 1)
    planted: List[Planted] = []

    patterns = rng.sample(POSITIVE, k=rng.randint(1, 3)) + rng.sample(NEGATIVE, k=rng.randint(2, 3))
    rng.shuffle(patterns)
    for pattern in patterns:
        if pattern in ("spouse_contractor", "nickname_disguise"):
            c = world._make_company(officers=[spouse.id], address=pi.home, address_type="residential",
                                    phone=spouse.phone if rng.random() < 0.5 else None)
            planted.append(Planted(c, pattern, True, expect_family=True))
        elif pattern == "holding_chain":
            pct_a = rng.choice([51.0, 60.0, 75.0, 100.0])
            pct_b = rng.choice([100.0, 80.0, 51.0])
            holdco = world._make_company(officers=[pi.id], address=pi.home, address_type="residential",
                                         owners=[(pi.id, pct_a), (spouse.id, 100.0 - pct_a)] if pct_a < 100 else [(pi.id, 100.0)])
            manager = rng.choice([p for p in world.people.values() if p.last != pi.last])
            vendor = world._make_company(officers=[manager.id], owners=[(holdco.id, pct_b), (manager.id, 100.0 - pct_b)]
                                         if pct_b < 100 else [(holdco.id, 100.0)])
            planted.append(Planted(vendor, pattern, True, expect_financial=True,
                                   expect_ownership_pct=round(pct_a * pct_b / 100.0, 1)))
        elif pattern == "straw_owner":
            adults = [world.people[h] for h in pi.household if h != pi.spouse]
            straw = adults[0] if adults else spouse
            c = world._make_company(officers=[straw.id], address=pi.home, address_type="residential")
            planted.append(Planted(c, pattern, True, expect_family=True))
        elif pattern == "self_officer":
            other = rng.choice(list(world.people.values()))
            c = world._make_company(officers=[other.id, pi.id], owners=[(other.id, 70.0), (pi.id, 30.0)])
            planted.append(Planted(c, pattern, True, expect_financial=True, expect_ownership_pct=30.0))
        elif pattern == "home_shell":
            other = rng.choice([p for p in world.people.values() if p.last != pi.last and p.home != pi.home])
            c = world._make_company(officers=[other.id], address=pi.home, address_type="residential", phone=pi.phone,
                                    formed=app_date - timedelta(days=rng.randint(5, 60)))
            planted.append(Planted(c, pattern, True, expect_financial=False))
        elif pattern == "surname_coincidence":
            same_last = [p for p in world.people.values() if p.last == pi.last and p.home != pi.home]
            if not same_last:
                stranger = rng.choice(list(world.people.values()))
                stranger = world._person(pi.last, stranger.sex, stranger.birth_year, world._street_address())
            else:
                stranger = rng.choice(same_last)
            c = world._make_company(officers=[stranger.id], address=stranger.home, address_type="residential")
            planted.append(Planted(c, pattern, False))
        elif pattern == "same_building":
            base = applicant.address.split(" Suite ")[0]
            tail = applicant.address.split(",", 1)[1]
            addr = f"{base} Suite {rng.randint(100, 900)},{tail}"
            other = rng.choice([p for p in world.people.values() if p.last != pi.last])
            c = world._make_company(officers=[other.id], address=addr, address_type="commercial")
            planted.append(Planted(c, pattern, False))
        elif pattern == "same_agent":
            other = rng.choice([p for p in world.people.values() if p.last != pi.last])
            c = world._make_company(officers=[other.id], agent=applicant.agent)
            planted.append(Planted(c, pattern, False))
        else:
            pool = [c for c in world.companies.values()
                    if c is not applicant and pi.id not in c.officers and spouse.id not in c.officers
                    and world.people[c.officers[0]].last != pi.last and c.address != pi.home
                    and c.address.split(" Suite ")[0] != applicant.address.split(" Suite ")[0]]
            planted.append(Planted(rng.choice(pool), "clean", False))

    for p in planted:
        p.presented_name = noisy_org_name(rng, p.company.name)
    return Case(applicant, pi, planted, app_date)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

@dataclass
class Outcome:
    pattern: str
    related: bool
    band: str                   # confirmed | review | none
    probability: float
    relationship_type: str
    immediate_family: bool
    self_dealing: bool
    ownership_pct: float
    expect_family: bool
    expect_financial: bool
    expect_ownership_pct: Optional[float]


async def run_case(engine: RelationshipEngine, world: World, rng: random.Random, case: Case) -> List[Outcome]:
    applicant = EntityRecord(name=noisy_org_name(rng, case.applicant.name), role="applicant",
                             addresses=[noisy_address(rng, case.applicant.address)], tax_ids=[case.applicant.tax_id])
    pi = EntityRecord(name=noisy_person_name(rng, case.pi), kind="person", role="key_personnel")
    if rng.random() < 0.4:   # sometimes the application lists a contact address for the PI
        pi.addresses.append(noisy_address(rng, case.pi.home))
    counterparties = []
    for p in case.counterparties:
        rec = EntityRecord(name=p.presented_name, role="contractor" if rng.random() < 0.6 else "vendor")
        if rng.random() < 0.6:
            rec.addresses.append(noisy_address(rng, p.company.address))
        if p.pattern == "nickname_disguise":
            # the application lists the spouse under a nickname / initial as the contractor's contact
            spouse = world.people[case.pi.spouse]
            rec.officers.append(noisy_person_name(rng, spouse))
        counterparties.append(rec)

    global LAST_INPUTS
    LAST_INPUTS = (applicant, [pi], counterparties)      # for debugging a surprising outcome
    result = await engine.analyze(applicant, counterparties, [pi], case.application_date)
    by_name: Dict[str, Any] = {}
    for f in result.findings:
        by_name[canonical_org_name(f.counterparty)] = ("confirmed", f)
    for f in result.review_recommended:
        by_name.setdefault(canonical_org_name(f.counterparty), ("review", f))

    outcomes = []
    for p in case.counterparties:
        band, f = by_name.get(canonical_org_name(p.presented_name), ("none", None))
        outcomes.append(Outcome(
            pattern=p.pattern, related=p.related, band=band,
            probability=f.probability if f else engine.prior,
            relationship_type=f.relationship_type if f else "",
            immediate_family=bool(f and f.immediate_family), self_dealing=bool(f and f.self_dealing),
            ownership_pct=f.indirect_ownership_percent if f else 0.0,
            expect_family=p.expect_family, expect_financial=p.expect_financial,
            expect_ownership_pct=p.expect_ownership_pct,
        ))
    return outcomes


def summarize(outcomes: List[Outcome]) -> Dict[str, Any]:
    tp = sum(1 for o in outcomes if o.related and o.band == "confirmed")
    fp = sum(1 for o in outcomes if not o.related and o.band == "confirmed")
    fn = sum(1 for o in outcomes if o.related and o.band != "confirmed")
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    f1 = 2 * precision * recall / max(1e-9, precision + recall)

    by_pattern: Dict[str, Dict[str, Any]] = {}
    for pattern in POSITIVE + NEGATIVE:
        rows = [o for o in outcomes if o.pattern == pattern]
        if not rows:
            continue
        confirmed = sum(1 for o in rows if o.band == "confirmed")
        review = sum(1 for o in rows if o.band == "review")
        entry: Dict[str, Any] = {"n": len(rows), "confirmed": confirmed / len(rows), "review": review / len(rows),
                                 "missed": (len(rows) - confirmed - review) / len(rows)}
        if pattern in POSITIVE:
            fam = [o for o in rows if o.expect_family]
            fin = [o for o in rows if o.expect_financial]
            if fam:
                entry["family_flag_accuracy"] = sum(1 for o in fam if o.immediate_family) / len(fam)
            if fin:
                entry["financial_flag_accuracy"] = sum(1 for o in fin if o.self_dealing) / len(fin)
            own = [o for o in rows if o.expect_ownership_pct is not None and o.band == "confirmed"]
            if own:
                entry["ownership_pct_mean_abs_error"] = statistics.mean(abs(o.ownership_pct - o.expect_ownership_pct) for o in own)
        by_pattern[pattern] = entry

    # Calibration
    brier = statistics.mean((o.probability - (1.0 if o.related else 0.0)) ** 2 for o in outcomes)
    bins: Dict[str, Dict[str, float]] = {}
    for lo in [0.0, 0.2, 0.35, 0.5, 0.65, 0.8, 0.9, 0.99]:
        hi = {0.0: 0.2, 0.2: 0.35, 0.35: 0.5, 0.5: 0.65, 0.65: 0.8, 0.8: 0.9, 0.9: 0.99, 0.99: 1.01}[lo]
        rows = [o for o in outcomes if lo <= o.probability < hi]
        if rows:
            bins[f"{lo:.2f}-{min(hi, 1.0):.2f}"] = {
                "n": len(rows),
                "predicted": round(statistics.mean(o.probability for o in rows), 3),
                "observed": round(sum(1 for o in rows if o.related) / len(rows), 3),
            }

    return {
        "counterparties": len(outcomes),
        "positives": sum(1 for o in outcomes if o.related),
        "negatives": sum(1 for o in outcomes if not o.related),
        "confirmed_band": {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4),
                           "tp": tp, "fp": fp, "fn": fn},
        "review_band": {"positives_routed_to_review": sum(1 for o in outcomes if o.related and o.band == "review"),
                        "negatives_routed_to_review": sum(1 for o in outcomes if not o.related and o.band == "review")},
        "false_positive_rate_on_negatives": round(fp / max(1, sum(1 for o in outcomes if not o.related)), 4),
        "by_pattern": by_pattern,
        "brier_score": round(brier, 4),
        "reliability": bins,
    }


def print_report(summary: Dict[str, Any], label: str) -> None:
    c = summary["confirmed_band"]
    print(f"\n=== {label} ===")
    print(f"counterparties: {summary['counterparties']}  positives: {summary['positives']}  negatives: {summary['negatives']}")
    print(f"confirmed band  precision {c['precision']:.3f}  recall {c['recall']:.3f}  F1 {c['f1']:.3f}   (tp {c['tp']} fp {c['fp']} fn {c['fn']})")
    print(f"false-positive rate on negatives: {summary['false_positive_rate_on_negatives']:.3f}")
    rb = summary["review_band"]
    print(f"review band: {rb['positives_routed_to_review']} positives, {rb['negatives_routed_to_review']} negatives")
    print(f"Brier score: {summary['brier_score']:.4f}")
    print(f"\n{'pattern':<22}{'n':>5}{'confirmed':>11}{'review':>9}{'missed':>9}  flags")
    for pattern, e in summary["by_pattern"].items():
        flags = []
        if "family_flag_accuracy" in e:
            flags.append(f"family {e['family_flag_accuracy']:.2f}")
        if "financial_flag_accuracy" in e:
            flags.append(f"financial {e['financial_flag_accuracy']:.2f}")
        if "ownership_pct_mean_abs_error" in e:
            flags.append(f"own% MAE {e['ownership_pct_mean_abs_error']:.1f}")
        kind = "+" if pattern in POSITIVE else "-"
        print(f"{kind} {pattern:<20}{e['n']:>5}{e['confirmed']:>11.2f}{e['review']:>9.2f}{e['missed']:>9.2f}  {', '.join(flags)}")
    print("\nreliability (predicted vs observed related rate):")
    for b, e in summary["reliability"].items():
        print(f"  {b:<12} n={e['n']:<5} predicted {e['predicted']:.3f}  observed {e['observed']:.3f}")


async def run_benchmark(cases: int, seed: int, coverage: float, vital_records: bool,
                        weights: Optional[Weights]) -> Dict[str, Any]:
    rng = random.Random(seed)
    world = World(rng)
    provider = SyntheticProvider(world, random.Random(seed + 1), coverage=coverage, vital_records=vital_records)
    engine = RelationshipEngine(provider, weights=weights)
    outcomes: List[Outcome] = []
    for _ in range(cases):
        case = build_case(world, rng)
        outcomes.extend(await run_case(engine, world, rng, case))
    summary = summarize(outcomes)
    summary["config"] = {"cases": cases, "seed": seed, "coverage": coverage, "vital_records": vital_records,
                         "weights": "custom" if weights else "default"}
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cases", type=int, default=200)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--coverage", type=float, default=1.0, help="share of entities the provider can find (0..1)")
    ap.add_argument("--no-vital-records", action="store_true", help="provider has no marriage/household data")
    ap.add_argument("--weights", help="JSON weights file from benchmarks.estimate_u")
    ap.add_argument("--json", help="write the summary to this path")
    args = ap.parse_args(argv)
    weights = load_weights(args.weights) if args.weights else None
    summary = asyncio.run(run_benchmark(args.cases, args.seed, args.coverage, not args.no_vital_records, weights))
    print_report(summary, f"synthetic benchmark (cases={args.cases}, seed={args.seed}, coverage={args.coverage}, "
                          f"vital_records={not args.no_vital_records}, weights={'custom' if weights else 'default'})")
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(summary, fh, indent=2)
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
