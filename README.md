## Usage

### Installation

```bash
$ touch .cache
$ uv sync
$ uv run scripts/setup.py
```

### Run

```bash
$ uv run benchmark --module apps.prism.prism_o4_mini ./scripts/benchmark/afc/apache-commons-compress_cc-delta-01_vuln_3.toml
```

The implementation of Prism is located in ./packages/crete/framework/agent/services/prism
Specifically, the implementation of progressive code retrieval is located in ./packages/crete/framework/agent/services/multi_retrieval