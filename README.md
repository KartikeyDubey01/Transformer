# Multi-Source Candidate Data Transformer

A deterministic, explainable pipeline that ingests candidate data from multiple heterogeneous sources and emits a single canonical profile per candidate, with full provenance and confidence tracking.

---
**🎥 [Watch the 2-minute Demo Video](https://drive.google.com/file/d/1_Klf-nz0V-6DWCWyuJnje4GfSPL9AR_E/view?usp=drive_link)**

## Quick Start

```bash
# Install dependencies (stdlib only — no external packages required)
python --version  # Python 3.10+ required

# Run end-to-end on sample inputs with default schema
python main.py sample_inputs/recruiter.csv \
               sample_inputs/ats_export.json \
               sample_inputs/recruiter_notes.txt \
               --output output/default_output.json

# Run with a custom output config (field rename, subset, E164 normalize)
python main.py sample_inputs/recruiter.csv \
               sample_inputs/ats_export.json \
               sample_inputs/recruiter_notes.txt \
               --config sample_inputs/config_recruiter_view.json \
               --output output/custom_config_output.json

# Run tests
python -m pytest tests/ -v
```

---

## Pipeline Architecture

```
INPUT FILES (.csv / .json / .txt)
        │
        ▼
   ┌─────────────────────────────────────┐
   │  DETECT  — auto-detect source type  │
   │           from file extension       │
   └─────────────┬───────────────────────┘
                 │
        ┌────────┴──────────┐
        ▼                   ▼
   CSVSource          ATSJsonSource      RecruiterNotesSource
   (structured)       (structured)       (unstructured, regex NLP)
        │                   │                    │
        └────────┬──────────┘                    │
                 │         ◄─────────────────────┘
                 ▼
   ┌──────────────────────────────────────────────────────┐
   │  EXTRACT → CIR (Canonical Intermediate Record)       │
   │  Each source emits a uniform dict:                   │
   │  {raw_name, emails[], phones[], links, location,     │
   │   skills[], experience[], education[], headline,     │
   │   years_experience, source, method}                  │
   └────────────────────────┬─────────────────────────────┘
                            │
                            ▼
   ┌──────────────────────────────────────────────────────┐
   │  NORMALIZE  (per-field, deterministic)               │
   │  • Emails → lowercase, RFC validation                │
   │  • Phones → E.164 (+CountryCode + digits)            │
   │  • Dates  → YYYY-MM                                  │
   │  • Country → ISO 3166 alpha-2                        │
   │  • Skills  → canonical name aliases (k8s→Kubernetes) │
   └────────────────────────┬─────────────────────────────┘
                            │
                            ▼
   ┌──────────────────────────────────────────────────────┐
   │  MERGE  (cross-source deduplication)                 │
   │  Match keys: email (exact) OR name (normalized)      │
   │  Conflict resolution: csv > ats_json > nlp_regex     │
   │  Lists (emails, phones, skills): union + dedup       │
   │  Provenance: every field tagged with source+method   │
   └────────────────────────┬─────────────────────────────┘
                            │
                            ▼
   ┌──────────────────────────────────────────────────────┐
   │  CONFIDENCE SCORE  (per-profile)                     │
   │  Base 0.5 + source count bonus + email/phone bonus   │
   │  Penalty for nlp_regex-only sources                  │
   │  Per-skill confidence based on source agreement      │
   └────────────────────────┬─────────────────────────────┘
                            │
                            ▼
   ┌──────────────────────────────────────────────────────┐
   │  PROJECT  (runtime config reshaping)                 │
   │  Field rename / remap / subset / normalizer override │
   │  Handles: null | omit | error on_missing policies    │
   └────────────────────────┬─────────────────────────────┘
                            │
                            ▼
   ┌──────────────────────────────────────────────────────┐
   │  VALIDATE  (schema check against config)             │
   │  Type enforcement, required field check              │
   │  Warnings logged — pipeline never hard-crashes       │
   └────────────────────────┬─────────────────────────────┘
                            │
                            ▼
                    JSON OUTPUT (stdout or file)
```

---

## Source Types Covered

| Source | Type | File | Parser |
|--------|------|------|--------|
| Recruiter CSV export | Structured | `.csv` | `CSVSource` — flexible column mapping |
| ATS JSON blob | Structured | `.json` | `ATSJsonSource` — remaps alien field names |
| Recruiter notes | Unstructured | `.txt` | `RecruiterNotesSource` — regex NLP |

---

## Runtime Config

Pass `--config <file.json>` to reshape output without touching code:

```json
{
  "fields": [
    { "path": "full_name", "type": "string", "required": true },
    { "path": "primary_email", "from": "emails[0]", "type": "string", "required": true },
    { "path": "phone", "from": "phones[0]", "type": "string", "normalize": "E164" },
    { "path": "skills", "from": "skills[].name", "type": "string[]", "normalize": "canonical" }
  ],
  "include_confidence": true,
  "include_provenance": false,
  "on_missing": "null"
}
```

Config capabilities:
- **Field subset** — only emit the fields you declare
- **Field rename** — `path` = output name, `from` = source path in canonical record
- **JSONPath-like access** — `emails[0]`, `skills[].name`, `experience[0].company`
- **Per-field normalizers** — `E164` for phones, `canonical` for skills
- **Missing policy** — `null` (emit null), `omit` (skip field), `error` (raise for required)
- **Toggle provenance/confidence** — `include_provenance`, `include_confidence`

---

## Output Schema (default)

```
candidate_id        string          deterministic SHA1 of name+email
full_name           string
emails              string[]        deduplicated union across sources
phones              string[]        E.164 format
location            {city, region, country}    country: ISO 3166-2
links               {linkedin, github, portfolio, other[]}
headline            string | null
years_experience    number | null
skills              [{name, confidence, sources[]}]
experience          [{company, title, start, end, summary}]  dates: YYYY-MM
education           [{institution, degree, field, end_year}]
provenance          [{field, source, method}]   where each value came from
overall_confidence  number          0.0 – 1.0
```

---

## Edge Cases Handled

| Situation | Handling |
|-----------|----------|
| Corrupt ATS entry (`ghost_entry_CORRUPT`) | Skipped: heuristic name corruption detector |
| Negative `years_exp` (-99) | Rejected: range check [0, 60] |
| Missing source file | Warning logged, pipeline continues |
| Invalid email (`not-an-email`) | Normalized to null, not emitted |
| Phone with no country context | Best-effort E.164 or null, never invented |
| Same candidate in 3 sources | Merged by email OR name key; union of lists |
| Text block with no name | Skipped with debug log |
| `on_missing: "error"` + required field | ValueError raised, caught by caller |
| Malformed JSON | Error logged, source skipped |

---

## Design Decisions & Trade-offs

**Why not LLM for text parsing?** Determinism requirement. Same inputs must always produce the same output. LLMs are non-deterministic and would require caching. Regex NLP is transparent and testable.

**Why union for skills instead of picking one source?** Skills are additive — an ATS might have "Kubernetes" while the CSV has "Docker". Merging gives a richer, more complete picture. Confidence per-skill tracks source agreement.

**What was deliberately left out (time-pressure scope):**
- GitHub API integration (URL parsing only, no live API call)
- LinkedIn scraping (requires session auth)
- PDF/DOCX resume parsing (would add `pdfplumber`/`python-docx` dependency)
- Fuzzy name matching (e.g. "Priya S." vs "Priya Sharma") — currently requires exact normalized match
- Database persistence — outputs JSON only

---

## Project Structure

```
transformer/
├── main.py                         # CLI entrypoint + pipeline orchestration
├── src/
│   ├── sources/
│   │   ├── __init__.py             # BaseSource + CIR schema definition
│   │   ├── csv_source.py           # Recruiter CSV parser
│   │   ├── json_source.py          # ATS JSON parser
│   │   └── text_source.py          # Recruiter notes NLP parser
│   ├── normalizers/
│   │   └── __init__.py             # E.164 phone, email, skills, dates, country
│   ├── merger/
│   │   └── merger.py               # Deduplication, conflict resolution, confidence
│   └── projector/
│       ├── projector.py            # Runtime config → output reshape
│       └── validator.py            # Schema + type validation
├── sample_inputs/
│   ├── recruiter.csv
│   ├── ats_export.json
│   ├── recruiter_notes.txt
│   ├── config_default.json
│   └── config_recruiter_view.json
├── output/
│   ├── default_output.json         # Full schema output
│   └── custom_config_output.json   # Custom config output
└── tests/
    └── test_pipeline.py            # 37 tests covering normalizers, merger, projector, edge cases
```

---

## Running Tests

```bash
pip install pytest
python -m pytest tests/ -v
# Expected: 37 passed
```
