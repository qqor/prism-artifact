# Prism

A multi-team LLM-based agent for automated vulnerability repair with progressive code retrieval.

## Installation

```bash
touch .cache
uv sync
uv run scripts/setup.py
```

## Usage

### Running Benchmarks

**Full Prism:**

```bash
uv run benchmark --module apps.prism.prism_o4_mini ./scripts/benchmark/afc/apache-commons-compress_cc-delta-01_vuln_3.toml
```

**Prism without FSG:**

```bash
uv run benchmark --module apps.prismwofsg.prismwofsg_o4_mini ./scripts/benchmark/afc/apache-commons-compress_cc-delta-01_vuln_3.toml
```

**Prism without PCR:**

```bash
uv run benchmark --module apps.prismwopcr.prismwopcr_o4_mini ./scripts/benchmark/afc/apache-commons-compress_cc-delta-01_vuln_3.toml
```

**Full Prism with Claude Sonnet 4.5:**

```bash
uv run benchmark --module apps.prism.prism_claude_sonnet_4_5 ./scripts/benchmark/afc/apache-commons-compress_cc-delta-01_vuln_3.toml
```

## Project Structure

| Component                        | Location                                                    |
|----------------------------------|-------------------------------------------------------------|
| Prism implementation             | `./packages/crete/framework/agent/services/prism`           |
| Progressive Code Retrieval (PCR) | `./packages/crete/framework/agent/services/multi_retrieval` |


### Evaluation Results

Evaluation results summaries are provided in `evaluation-results/Prism Evaluation.xlsx`, containing data from 5 runs of each baseline. The spreadsheet includes 4 sheets:

- **Sheets 1-3**: Results corresponding to each research question (RQ1, RQ2, RQ3)
- **Sheet 4**: Vulnerability type mappings (provided due to inconsistent naming in the original dataset)

Correct patches are highlighted in color, as are manually validated incorrect patches.