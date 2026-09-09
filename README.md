# SkillSift

Score your CV against a job description, keep track of what you applied to, and
find out which skills you keep failing to have.

I built this while applying for graduate engineering roles in the UK. After
about thirty applications I had two problems that a spreadsheet was not solving:
I could not tell at a glance whether a posting was actually worth the hour it
takes to tailor a CV, and I had no idea which skills were costing me postings
over and over. SkillSift answers both, and it does it offline — your CV never
leaves your machine.

```
$ skillsift match my-cv.md junior-ml-engineer.md --save

Junior ML Engineer
  ████████████████········  68%  (worth applying)
  skills 68%

You have
  CI/CD, Docker, Linux, PyTorch, Python, SQL, Testing

Missing — required
  ✗ Machine Learning
      "Junior Machine Learning Engineer"
  ✗ TensorFlow
      "Requirements - Solid Python and SQL - Hands-on experience with PyTorch or TensorFlow…"

Missing — nice to have
  AWS, GCP, Kubernetes, Rust

By category
  infra        3/6  ██████······
  languages    2/3  ████████····
  ml           1/3  ████········
  practice     1/1  ████████████

On your CV but not asked for
  Computer Vision, Flask, Git, NumPy, PostgreSQL, REST APIs, pandas
```

Every gap quotes the line of the posting it came from. A score you cannot argue
with is a score nobody trusts.

## Install

```bash
git clone https://github.com/aniketmor218/skillsift.git
cd skillsift
pip install -e ".[dev,pdf]"
```

Python 3.10+. Two runtime dependencies: Flask and PyYAML. PDF reading is
optional and only imports `pypdf` if you actually hand it a PDF.

## Use it

```bash
# score a CV against a posting
skillsift match my-cv.md posting.md

# score it and add it to the tracker
skillsift match my-cv.md posting.md --title "Junior ML Engineer" --company Acme --save

# what have I applied to?
skillsift list
skillsift list --status interview

# move an application along
skillsift status 3 interview --note "phone screen Thursday"

# the payoff: what am I missing most often?
skillsift gaps
```

```
Skills you are missing most often

  Kubernetes           ██████████████████ 7
  AWS                  █████████████·····  5
  TypeScript           ████████··········  3
```

`match` exits `0` above the pass threshold and `1` below it, so it composes:

```bash
skillsift match cv.md posting.md --json | jq '.missing_required'
skillsift match cv.md posting.md || echo "probably not worth the evening"
```

### Web interface

```bash
skillsift serve            # http://127.0.0.1:5000
```

Paste a posting, get the same breakdown in a browser, and click through your
tracked applications. There is a JSON endpoint too:

```bash
curl -s localhost:5000/api/match \
  -H 'content-type: application/json' \
  -d '{"cv": "...", "jd": "..."}' | jq
```

### Docker

```bash
docker build -t skillsift .
docker run -p 8000:8000 -v skillsift-data:/data skillsift
```

Runs under gunicorn as a non-root user with the database on a volume, so your
history survives a redeploy. `GET /api/health` is wired to `HEALTHCHECK`.

## How the scoring works

```
score = 0.8 × weighted skill coverage + 0.2 × IDF keyword coverage
```

**Skills are phrases, not words.** Every alias in `skillsift/data/skills.yml` is
compiled into one trie, and a document is scanned once over token n-grams with
longest-match-wins. That is why "machine learning engineer" does not also fire a
separate hit for "machine learning", and why the skill `R` does not match inside
`Rust` — the mistake a naive `if skill in text` makes on its first real input.

**Where a skill appears decides what it is worth.** A posting is not a bag of
words. "You must have 3 years of Python" and "Rust would be a bonus" mean
different things, and the difference is almost always a heading. Headings are
classified into `required` / `preferred` / `context`, required skills are
weighted 3× preferred, and a skill that appears in two sections keeps its
strongest emphasis. Skills that only ever show up in a benefits blurb are
demoted rather than dropped.

**The keyword term only participates once it means something.** IDF is computed
over the postings you have saved, so common boilerplate ("fast-paced
environment") is discounted and terms specific to this posting are not. Below
five stored postings the corpus is too thin for that to be anything but noise,
so the term is dropped and the skill score is used alone. The IDF is about
fifteen lines of arithmetic in `text.py` — pulling in scikit-learn to compute
one logarithm would have been a poor trade.

## Layout

```
skillsift/
├── text.py          tokenising, the phrase-matching trie, IDF
├── skills.py        the taxonomy, and extracting skills with evidence spans
├── documents.py     reading files; splitting a posting into weighted sections
├── matcher.py       scoring — the only module that knows what a "score" is
├── store.py         SQLite, with versioned migrations
├── report.py        terminal rendering and JSON output
├── cli.py           argparse entry point
├── data/skills.yml  the taxonomy — add skills here, not in the code
└── web/             Flask app factory, routes, templates
```

Each module has one job and the dependencies point one way: `text` knows
nothing about skills, `skills` knows nothing about scoring, `matcher` knows
nothing about SQLite or terminals. That is what makes the whole thing testable
without mocks.

## Adding skills

The matcher is data-driven. To teach it something new, edit
`skillsift/data/skills.yml` — no code change:

```yaml
languages:
  Elixir: [elixir, phoenix framework]
```

`skillsift skills --category languages` lists what it currently knows.

## Tests

```bash
pytest --cov=skillsift    # 78 tests, 93% coverage
ruff check skillsift tests
```

Several tests are named regressions, because they are: bullet lines being
swallowed as section headings, a word-boundary bug that made the heading
"Requirements" unmatchable in its plural form, and re-scoring a posting
silently resetting an application you had already moved to "interview". CI runs
the suite and the linter on Python 3.10, 3.11 and 3.12.

## Known limitations

These are honest, not hidden:

- **Alternatives are not modelled.** "PyTorch or TensorFlow" produces two
  requirements, so knowing one still reads as a gap. Fixing it properly means
  parsing the conjunction, not special-casing the word "or".
- **No semantic matching.** "built data pipelines" does not match the skill
  `ETL` unless the alias is in the taxonomy. Embeddings would fix this and cost
  the offline, dependency-light property that makes the tool pleasant to run.
- **Skills only, not seniority.** It cannot tell "3 years of Python" from
  "exposure to Python", and it does not read years of experience at all.
- **English-language postings**, and text-layer PDFs only — a scanned CV needs
  OCR, and the error message says so rather than silently scoring zero.

The score is guidance, not gatekeeping. Apply anyway if you want the job.

## Licence

MIT.
