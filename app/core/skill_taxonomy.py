"""
Skill equivalence / adjacency taxonomy.

Phase C and the legacy scorer matched skills with
`skill.casefold() in candidate_skills`, which means "Postgres" misses
"PostgreSQL", "JS" misses "JavaScript", and "AWS" misses "Amazon Web
Services". The client asked for "related skill equivalents", so matching
needs three tiers rather than one boolean:

    EXACT       the requirement term itself appears
    EQUIVALENT  a known alias of the same skill appears  (full credit)
    ADJACENT    a different-but-related skill appears    (partial credit)

This module is deliberately data-driven and contains no model calls. It is
the same on every run, which is what makes criterion scores reproducible and
defensible to a client — an LLM synonym guess is neither.

Extending it is a data edit, not a code change: add to `_ALIAS_GROUPS` for
"these strings mean the same skill", or `_ADJACENCY_GROUPS` for "these are
neighbours". Nothing else needs to know.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# How much credit an adjacent (not equivalent) skill earns. 0.55 is a
# deliberate choice: enough that a Postgres-for-MySQL candidate is visibly
# better than one with no database at all, not enough to pass as a match.
ADJACENT_CREDIT = 0.55

# Terms this short are matched as whole tokens only, never as substrings.
# Without this, "R" matches every word containing an r and "go" matches
# "google", "goal" and "category".
SHORT_TERM_LEN = 3


# ---------------------------------------------------------------------------
# Alias data — surface forms that mean the same skill.
# The first entry of each group is the canonical label used in output.
# ---------------------------------------------------------------------------

_ALIAS_GROUPS: list[list[str]] = [
    # Languages / runtimes
    ["javascript", "js", "ecmascript", "es6", "es2015"],
    ["typescript", "ts"],
    ["python", "python3", "py"],
    ["c#", "csharp", "c sharp", ".net c#"],
    ["c++", "cpp", "c plus plus"],
    ["golang", "go lang", "go"],
    ["node.js", "node", "nodejs"],
    ["java", "core java", "java se"],
    ["kotlin"],
    ["rust"],
    ["ruby"],
    ["php"],
    ["scala"],
    ["r", "r language"],
    ["matlab"],
    ["sql", "structured query language"],
    ["pl/sql", "plsql"],
    ["t-sql", "tsql", "transact-sql"],
    ["shell scripting", "bash", "shell", "sh scripting"],
    ["powershell", "power shell"],

    # Datastores
    ["postgresql", "postgres", "psql", "postgre sql"],
    ["mysql", "my sql"],
    ["microsoft sql server", "sql server", "mssql", "ms sql"],
    ["oracle database", "oracle db", "oracle"],
    ["mongodb", "mongo"],
    ["redis"],
    ["elasticsearch", "elastic search", "elk", "opensearch"],
    ["cassandra", "apache cassandra"],
    ["dynamodb", "dynamo db"],
    ["snowflake"],
    ["bigquery", "big query"],
    ["redshift", "amazon redshift"],
    ["databricks"],

    # Cloud
    ["aws", "amazon web services"],
    ["azure", "microsoft azure", "ms azure"],
    ["gcp", "google cloud", "google cloud platform"],
    ["s3", "amazon s3"],
    ["ec2", "amazon ec2"],
    ["lambda", "aws lambda"],
    ["azure functions"],
    ["cloud formation", "cloudformation"],
    ["terraform", "hashicorp terraform"],
    ["kubernetes", "k8s", "kube"],
    ["docker", "containerisation", "containerization", "containers"],
    ["openshift", "red hat openshift"],
    ["helm"],

    # Data / ML
    ["machine learning", "ml"],
    ["deep learning", "dl", "neural networks"],
    ["natural language processing", "nlp"],
    ["computer vision", "cv (computer vision)", "image processing"],
    ["large language models", "llm", "llms", "genai", "generative ai"],
    ["scikit-learn", "sklearn", "scikit learn"],
    ["tensorflow", "tf"],
    ["pytorch", "torch"],
    ["pandas"],
    ["numpy"],
    ["apache spark", "spark", "pyspark"],
    ["apache kafka", "kafka"],
    ["apache airflow", "airflow"],
    ["etl", "extract transform load", "elt"],
    ["power bi", "powerbi", "microsoft power bi"],
    ["tableau"],
    ["looker"],
    ["qlik", "qlikview", "qlik sense"],

    # Web / frontend
    ["react", "react.js", "reactjs"],
    ["angular", "angular.js", "angularjs"],
    ["vue", "vue.js", "vuejs"],
    ["next.js", "nextjs"],
    ["svelte"],
    ["html", "html5"],
    ["css", "css3"],
    ["tailwind", "tailwind css", "tailwindcss"],
    ["bootstrap"],
    ["rest api", "rest", "restful api", "restful", "rest apis"],
    ["graphql", "graph ql"],
    ["grpc"],
    ["microservices", "micro services", "microservice architecture"],

    # Backend frameworks
    ["django"],
    ["flask"],
    ["fastapi", "fast api"],
    ["spring boot", "springboot", "spring"],
    [".net", "dotnet", ".net core", "asp.net"],
    ["express", "express.js", "expressjs"],
    ["rails", "ruby on rails"],
    ["laravel"],

    # Practice / process
    ["ci/cd", "cicd", "continuous integration", "continuous delivery", "continuous deployment"],
    ["jenkins"],
    ["github actions", "gh actions"],
    ["gitlab ci", "gitlab-ci"],
    ["azure devops", "vsts", "tfs"],
    ["devops"],
    ["site reliability engineering", "sre"],
    ["agile", "agile methodology", "agile delivery"],
    ["scrum", "scrum master"],
    ["kanban"],
    ["safe", "scaled agile framework"],
    ["jira", "atlassian jira"],
    ["confluence"],
    ["git", "version control", "source control"],
    ["test driven development", "tdd"],
    ["unit testing", "unit tests"],
    ["selenium"],
    ["cypress"],
    ["playwright"],
    ["pytest"],
    ["junit"],
    ["postman"],

    # Security / GRC — relevant to the consulting context this runs in
    ["information security", "infosec", "cyber security", "cybersecurity"],
    ["identity and access management", "iam"],
    ["security operations centre", "security operations center", "soc"],
    ["penetration testing", "pen testing", "pentest", "ethical hacking"],
    ["vulnerability assessment", "va", "vulnerability management"],
    ["iso 27001", "iso27001", "iso/iec 27001"],
    ["soc 2", "soc2", "soc ii"],
    ["pci dss", "pci-dss", "pci"],
    ["gdpr", "general data protection regulation"],
    ["hipaa"],
    ["sox", "sarbanes-oxley", "sarbanes oxley"],
    ["nist", "nist csf", "nist cybersecurity framework"],
    ["risk assessment", "risk analysis"],
    ["internal audit", "internal auditing"],
    ["governance risk and compliance", "grc"],
    ["business continuity planning", "bcp"],
    ["disaster recovery", "dr"],

    # Business / functional
    ["business analysis", "business analyst", "ba"],
    ["project management", "project manager", "pm"],
    ["programme management", "program management", "programme manager", "program manager"],
    ["stakeholder management", "stakeholder engagement"],
    ["requirements gathering", "requirement gathering", "requirements elicitation"],
    ["change management"],
    ["vendor management", "supplier management"],
    ["financial modelling", "financial modeling"],
    ["data analysis", "data analytics"],
    ["data engineering"],
    ["data science"],
    ["business intelligence", "bi"],
    ["erp", "enterprise resource planning"],
    ["sap"],
    ["salesforce", "sfdc"],
    ["workday"],
    ["oracle fusion"],
    ["servicenow", "service now"],

    # Certifications
    ["pmp", "project management professional"],
    ["prince2", "prince 2"],
    ["cissp"],
    ["cisa"],
    ["cism"],
    ["ceh", "certified ethical hacker"],
    ["aws certified solutions architect", "aws solutions architect"],
    ["azure administrator", "az-104"],
    ["ckad", "certified kubernetes application developer"],
    ["cka", "certified kubernetes administrator"],
    ["csm", "certified scrum master"],
    ["ca", "chartered accountant"],
    ["cpa", "certified public accountant"],
    ["cfa", "chartered financial analyst"],
    ["mba", "master of business administration"],
    ["b.tech", "btech", "bachelor of technology", "be", "b.e."],
    ["m.tech", "mtech", "master of technology"],
    ["b.sc", "bsc", "bachelor of science"],
    ["m.sc", "msc", "master of science"],
    ["b.com", "bcom", "bachelor of commerce"],
    ["bca", "bachelor of computer applications"],
    ["mca", "master of computer applications"],
]

# ---------------------------------------------------------------------------
# Adjacency data — canonical skills that are neighbours, not synonyms.
# Membership in a group means "partial credit for each other".
# ---------------------------------------------------------------------------

_ADJACENCY_GROUPS: list[list[str]] = [
    # Relational databases are broadly transferable between engines.
    ["postgresql", "mysql", "microsoft sql server", "oracle database", "sql"],
    # Cloud providers.
    ["aws", "azure", "gcp"],
    # Container orchestration and its ecosystem.
    ["kubernetes", "docker", "openshift", "helm"],
    # IaC.
    ["terraform", "cloud formation", "helm"],
    # Frontend SPA frameworks.
    ["react", "angular", "vue", "svelte", "next.js"],
    # Python web frameworks.
    ["django", "flask", "fastapi"],
    # JVM / .NET backend stacks.
    ["java", "spring boot", "kotlin", "scala"],
    [".net", "c#"],
    # Statically typed / dynamically typed JS.
    ["javascript", "typescript", "node.js"],
    # BI tooling.
    ["power bi", "tableau", "looker", "qlik", "business intelligence"],
    # Big-data / pipeline tooling.
    ["apache spark", "apache kafka", "apache airflow", "etl", "databricks"],
    # Warehouses.
    ["snowflake", "bigquery", "redshift", "databricks"],
    # ML stack.
    ["machine learning", "deep learning", "tensorflow", "pytorch", "scikit-learn"],
    ["natural language processing", "large language models", "deep learning"],
    # NoSQL.
    ["mongodb", "cassandra", "dynamodb", "redis"],
    # CI/CD implementations.
    ["ci/cd", "jenkins", "github actions", "gitlab ci", "azure devops"],
    # Delivery methodology.
    ["agile", "scrum", "kanban", "safe"],
    # Test automation.
    ["selenium", "cypress", "playwright"],
    ["pytest", "junit", "unit testing", "test driven development"],
    # Security domains.
    ["penetration testing", "vulnerability assessment", "information security"],
    ["iso 27001", "soc 2", "nist", "pci dss"],
    ["sox", "internal audit", "governance risk and compliance", "risk assessment"],
    ["gdpr", "hipaa", "pci dss"],
    # Management adjacency.
    ["project management", "programme management", "change management"],
    ["business analysis", "requirements gathering", "stakeholder management"],
    # Data roles.
    ["data analysis", "data engineering", "data science", "business intelligence"],
    # ERP platforms.
    ["sap", "erp", "oracle fusion", "workday"],
    # Degree equivalence-ish (a BCA and a B.Tech are not the same, but for a
    # "bachelor's in a technical field" criterion they are neighbours).
    ["b.tech", "b.sc", "bca", "b.com"],
    ["m.tech", "m.sc", "mca", "mba"],
]


# ---------------------------------------------------------------------------
# Index construction (module import time, cheap — pure dict building)
# ---------------------------------------------------------------------------

def _norm(text: str) -> str:
    """Lowercase and collapse whitespace. Punctuation is preserved because it
    is load-bearing in skill names: 'c#', 'c++', '.net', 'ci/cd', 'node.js'."""
    return re.sub(r"\s+", " ", (text or "").strip().casefold())


_SURFACE_TO_CANONICAL: dict[str, str] = {}
_CANONICAL_TO_SURFACES: dict[str, list[str]] = {}

for _group in _ALIAS_GROUPS:
    _canonical = _norm(_group[0])
    _surfaces = []
    for _surface in _group:
        _key = _norm(_surface)
        if _key and _key not in _SURFACE_TO_CANONICAL:
            _SURFACE_TO_CANONICAL[_key] = _canonical
        if _key not in _surfaces:
            _surfaces.append(_key)
    _CANONICAL_TO_SURFACES.setdefault(_canonical, []).extend(
        s for s in _surfaces if s not in _CANONICAL_TO_SURFACES.get(_canonical, [])
    )

_ADJACENCY: dict[str, set[str]] = {}
for _group in _ADJACENCY_GROUPS:
    _members = {_norm(m) for m in _group}
    for _member in _members:
        _ADJACENCY.setdefault(_member, set()).update(_members - {_member})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@dataclass
class TermMatch:
    """Outcome of looking for one requirement term in one body of text."""
    term: str
    kind: str                # "EXACT" | "EQUIVALENT" | "ADJACENT" | "NONE"
    credit: float            # 1.0 exact/equivalent, ADJACENT_CREDIT adjacent, 0.0 none
    matched_surface: str = ""
    char_start: int | None = None
    char_end: int | None = None

    @property
    def found(self) -> bool:
        return self.kind != "NONE"


def canonicalize(term: str) -> str:
    """Map a surface form to its canonical label, or return it normalized."""
    key = _norm(term)
    return _SURFACE_TO_CANONICAL.get(key, key)


def equivalents(term: str) -> list[str]:
    """Every surface form that means the same skill as `term`, itself included."""
    canonical = canonicalize(term)
    surfaces = list(_CANONICAL_TO_SURFACES.get(canonical, []))
    key = _norm(term)
    if key and key not in surfaces:
        surfaces.insert(0, key)
    if canonical not in surfaces:
        surfaces.insert(0, canonical)
    return surfaces


def adjacent(term: str) -> list[str]:
    """Canonical labels of related-but-different skills."""
    return sorted(_ADJACENCY.get(canonicalize(term), set()))


def is_known(term: str) -> bool:
    """True when the taxonomy has an opinion about this term at all."""
    canonical = canonicalize(term)
    return canonical in _CANONICAL_TO_SURFACES or canonical in _ADJACENCY


def _pattern_for(surface: str) -> re.Pattern[str]:
    """
    Build a boundary-aware pattern for a surface form.

    Skill names contain regex metacharacters ('c++', 'c#', '.net'), so the
    surface is escaped and the boundaries are asserted with lookarounds on
    word characters rather than `\\b` — `\\b` behaves wrongly next to '+' and
    '#', which are non-word characters themselves.
    """
    escaped = re.escape(surface)
    # Allow a space or hyphen where the surface has a space: "power bi"
    # should also match "power-bi".
    escaped = escaped.replace(r"\ ", r"[\s\-]+")
    return re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", re.IGNORECASE)


_PATTERN_CACHE: dict[str, re.Pattern[str]] = {}


def _search(surface: str, haystack: str) -> re.Match[str] | None:
    if not surface or not haystack:
        return None
    pattern = _PATTERN_CACHE.get(surface)
    if pattern is None:
        pattern = _pattern_for(surface)
        _PATTERN_CACHE[surface] = pattern
    return pattern.search(haystack)


def find_term(term: str, haystack: str) -> TermMatch:
    """
    Look for `term` in `haystack`, escalating outwards: the literal term,
    then its aliases, then its neighbours. Returns the strongest hit.

    `haystack` should be the raw document text — offsets in the result are
    into that string, so evidence can be quoted with its position.
    """
    term_norm = _norm(term)
    if not term_norm or not haystack:
        return TermMatch(term=term, kind="NONE", credit=0.0)

    # Very short terms ("r", "go", "ba") are token-matched only; the boundary
    # pattern already does that, but they are also excluded from adjacency
    # expansion because a two-letter neighbour match is almost always noise.
    match = _search(term_norm, haystack)
    if match:
        return TermMatch(
            term=term, kind="EXACT", credit=1.0, matched_surface=match.group(0),
            char_start=match.start(), char_end=match.end(),
        )

    for surface in equivalents(term):
        if surface == term_norm:
            continue
        match = _search(surface, haystack)
        if match:
            return TermMatch(
                term=term, kind="EQUIVALENT", credit=1.0, matched_surface=match.group(0),
                char_start=match.start(), char_end=match.end(),
            )

    if len(term_norm) >= SHORT_TERM_LEN:
        for neighbour in adjacent(term):
            for surface in _CANONICAL_TO_SURFACES.get(neighbour, [neighbour]):
                match = _search(surface, haystack)
                if match:
                    return TermMatch(
                        term=term, kind="ADJACENT", credit=ADJACENT_CREDIT,
                        matched_surface=match.group(0),
                        char_start=match.start(), char_end=match.end(),
                    )

    return TermMatch(term=term, kind="NONE", credit=0.0)


# ---------------------------------------------------------------------------
# Requirement text -> searchable terms
# ---------------------------------------------------------------------------

# Words that carry no matching signal. A criterion label is a sentence from a
# JD ("5+ years of hands-on experience with PostgreSQL and Redis"), so the
# terms have to be mined out of it.
_STOPWORDS = {
    "a", "an", "and", "or", "the", "of", "in", "on", "at", "to", "for", "with",
    "using", "use", "used", "strong", "solid", "proven", "hands", "hands-on",
    "experience", "experienced", "knowledge", "understanding", "working",
    "work", "years", "year", "yrs", "plus", "minimum", "min", "least",
    "excellent", "good", "very", "must", "should", "have", "has", "is", "are",
    "be", "been", "ability", "able", "skills", "skill", "expertise", "familiar",
    "familiarity", "demonstrated", "track", "record", "background", "such",
    "as", "including", "include", "etc", "similar", "related", "equivalent",
    "preferred", "required", "desirable", "mandatory", "candidate", "role",
    "team", "environment", "across", "within", "from", "by", "over", "more",
    "than", "well", "highly", "deep", "broad", "e.g", "ie", "i.e", "eg",
    # Filler nouns that survive extraction from a JD sentence but carry no
    # matching signal of their own: "a Bachelor's degree in Computer Science"
    # should be checked against the degree and the field, not against the
    # word "degree".
    "degree", "level", "area", "areas", "domain", "domains", "field",
    "fields", "discipline", "based", "plus", "any", "other", "various",
    "multiple", "large", "small", "scale", "end", "full", "part", "new",
    "using", "delivering", "managing", "leading", "building", "developing",
    "proficiency", "proficient", "competent", "advanced", "intermediate",
    "sound", "practical", "extensive", "significant", "substantial",
}


def extract_terms(text: str, limit: int = 12) -> list[str]:
    """
    Mine candidate match terms out of a requirement label.

    Multi-word taxonomy entries are recognised first (so "power bi" survives
    as one term instead of becoming "power" and "bi"), then remaining
    non-stopword tokens are kept in order.
    """
    normalized = _norm(text)
    if not normalized:
        return []

    terms: list[str] = []
    consumed_spans: list[tuple[int, int]] = []

    # Longest-first so "microsoft sql server" wins over "sql".
    known = sorted(_SURFACE_TO_CANONICAL, key=len, reverse=True)
    for surface in known:
        if len(surface) < SHORT_TERM_LEN:
            continue
        match = _search(surface, normalized)
        if not match:
            continue
        span = (match.start(), match.end())
        if any(span[0] < end and start < span[1] for start, end in consumed_spans):
            continue
        consumed_spans.append(span)
        canonical = _SURFACE_TO_CANONICAL[surface]
        if canonical not in terms:
            terms.append(canonical)

    if len(terms) >= limit:
        return terms[:limit]

    # Whatever is left: bare tokens, punctuation-trimmed, stopwords dropped.
    remaining = normalized
    for start, end in sorted(consumed_spans, reverse=True):
        remaining = remaining[:start] + " " + remaining[end:]
    for token in re.split(r"[^A-Za-z0-9+#./\-]+", remaining):
        cleaned = token.strip(".-/")
        if len(cleaned) < SHORT_TERM_LEN or cleaned in _STOPWORDS:
            continue
        if cleaned.isdigit():
            continue
        canonical = canonicalize(cleaned)
        if canonical not in terms:
            terms.append(canonical)
        if len(terms) >= limit:
            break

    return terms[:limit]
