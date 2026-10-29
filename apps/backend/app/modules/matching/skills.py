import re

# Equivalence only, not a technology hierarchy. Short ambiguous Go/R/C mentions
# are not inferred from prose. Explicit structured skills can still name them.
ALIASES = {
    "python": ("Python",),
    "javascript": ("JavaScript", "JS"),
    "typescript": ("TypeScript", "TS"),
    "postgresql": ("PostgreSQL", "Postgres"),
    "machine_learning": ("machine learning", "ML"),
    "natural_language_processing": ("natural language processing", "NLP"),
    "react": ("React", "React.js", "ReactJS"),
    "nodejs": ("Node.js", "NodeJS"),
    "fastapi": ("FastAPI",),
    "sql": ("SQL",),
    "java": ("Java",),
    "aws": ("AWS", "Amazon Web Services"),
    "azure": ("Azure", "Microsoft Azure"),
    "docker": ("Docker",),
    "kubernetes": ("Kubernetes", "K8s"),
    "git": ("Git",),
    "rest": ("REST", "RESTful"),
    "html": ("HTML", "HTML5"),
    "css": ("CSS", "CSS3"),
    "excel": ("Excel", "Microsoft Excel"),
    "power_bi": ("Power BI",),
    "tableau": ("Tableau",),
    "tensorflow": ("TensorFlow",),
    "pytorch": ("PyTorch",),
    "scikit_learn": ("scikit-learn", "sklearn"),
    "csharp": ("C#", "C sharp"),
    "cpp": ("C++",),
    "dotnet": (".NET", "dotnet"),
    "golang": ("Golang",),
    "ruby": ("Ruby",),
    "django": ("Django",),
    "flask": ("Flask",),
    "terraform": ("Terraform",),
    "selenium": ("Selenium",),
    "playwright": ("Playwright",),
    "pytest": ("pytest",),
    "salesforce": ("Salesforce",),
    "sap": ("SAP",),
    "figma": ("Figma",),
    "seo": ("SEO", "search engine optimization"),
    "automation": ("workflow automation", "process automation"),
    "data_analysis": ("data analysis", "data analytics"),
    "project_management": ("project management",),
    "customer_support": ("customer support", "technical support"),
}
LOOKUP = {alias.casefold(): key for key, aliases in ALIASES.items() for alias in aliases}
LOOKUP.update({"go": "golang", "c#": "csharp", "c++": "cpp"})
PATTERNS = [
    (key, re.compile(r"(?<![\w+#])" + re.escape(alias) + r"(?![\w+#])", re.I))
    for key, aliases in ALIASES.items()
    for alias in sorted(aliases, key=len, reverse=True)
]


def normalize_skill(value):
    cleaned = " ".join(value.split()).casefold()
    return LOOKUP.get(cleaned, re.sub(r"\s+", "_", cleaned))


def skill_name(key):
    return ALIASES.get(key, (key.replace("_", " "),))[0]


def mentions(text):
    found = {}
    for key, pattern in PATTERNS:
        match = pattern.search(text)
        if match and key not in found:
            found[key] = (match.start(), match.end(), match.group())
    return found


def negative_mention(text, start):
    prefix = text[max(0, start - 55) : start].casefold()
    return bool(
        re.search(
            r"(?:no|not|without|lack(?:ing)?|do not have|don.t (?:have|know))\s+(?:\w+\s+){0,4}$",
            prefix,
        )
    )
