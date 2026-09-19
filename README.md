# Shipping Document Checker

A minimal, explainable shipping document verification pipeline for the SDOC
hackathon. It implements only the required basic workflow:

- read every participant-bundle email JSON record;
- classify emails into `BL_COMPARISON`, `SI_REQUEST`, `INVOICE_QUERY`,
  `GENERAL`, or `SPAM`;
- process only `BL_COMPARISON` emails;
- read plain-text SI and BL attachments;
- extract and compare the seven required shipment fields;
- preserve the SI and BL values for every mismatch;
- send missing, unsupported, or unreliable cases to manual review;
- generate a submission matching `sample_submission.json`.

PDF, DOCX, XLSX, scanned documents, and OCR are outside this basic version.
Those attachments are marked `NEEDS_REVIEW` instead of being guessed.

## Required fields

1. `shipper`
2. `consignee`
3. `notify_party`
4. `port_of_loading`
5. `port_of_discharge`
6. `container_count`
7. `gross_weight_kg`

The parser uses a fixed alias table for labels such as `Load Port`, `POL`, and
`Port of Loading`. Normalization is limited to whitespace, letter case,
Unicode, container count, and KG number formatting. It does not use fuzzy
matching.

## Run

### Web interface

```bash
cd web-app
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
streamlit run app.py
```

Open `http://localhost:8501`. The interface includes inbox analysis, recorded
processing errors with retry, a human review dashboard, comparison results,
and JSON/CSV/PDF exports.

### Command line

Python 3.10 or newer is sufficient for the command-line pipeline.

```bash
cd web-app
python3 run.py --bundle /path/to/sdoc-hackathon-bundle
```

The repository's bundled sample data at `local-data/participant-bundle` is used
automatically, so the shorter command works after cloning:

```bash
cd web-app
python3 run.py
```

The command writes:

- `output/submission.json`: the official submission shape;
- `output/results.json`: extracted values, mismatch evidence, and manual-review details;
- `output/summary.json`: run counts.
- `output/errors.json`: processing error and retry history;
- `output/review_decisions.json`: saved human review decisions.

Generated output and hackathon datasets are excluded from Git. If an official
local evaluation server is already running, submit through its public endpoint:

```bash
python3 run.py --bundle /path/to/sdoc-hackathon-bundle \
  --submit-url http://localhost:8080
```

The application reads only `local-data/participant-bundle`. It does not read
organizer evaluation files or a private answer key.
