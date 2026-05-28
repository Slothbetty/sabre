# StreamLens

StreamLens is an open-source ABR simulation environment for multi-region buffering, seeking, and prefetching. It extends [SABRE](https://github.com/UMass-LIDS/sabre) with nonlinear buffering, configurable seek and prefetch scenarios, session-replay and chunk-replay workflows, and a browser-based viewer for comparing ABR algorithms.

## Requirements

- Python >= 3.10
- `numpy` (see `requirements.txt`)

## Quick Start

```bash
git clone https://github.com/Slothbetty/sabre.git
cd sabre
pip install -r requirements.txt
cd src
```

**Single ABR run:**
```bash
python run_comparison.py -n synthetic/network.json -m synthetic/movie.json -a bola -o results.json
python serve_viewer.py
# Open http://localhost:8000/viewer/view_comparison.html and load results.json
```

**Cross-ABR comparison across seek scenarios (main workflow from the paper):**
```bash
python run_comparison.py \
  -n synthetic/network.json -m synthetic/movie.json \
  -sc synthetic/seeks.json,synthetic/seeks_prefetch_hit.json,synthetic/seeks_mixed.json,synthetic/seeks_linear_hit_nonlinear_miss.json,synthetic/seeks_linear_miss_nonlinear_hit.json \
  -pc synthetic/test_prefetch_config.json \
  -a all -o synthetic/results
python serve_viewer.py
# Open http://localhost:8000/viewer/view_comparison.html and load synthetic/results/comparison_summary.json
```

## Docker

```bash
docker build -t streamlens .
docker run --rm streamlens
```

## Documentation

Full documentation and workflow guides are in [src/README.md](src/README.md).

## License

BSD 2-Clause — see [LICENSE](LICENSE).

## Based On

StreamLens builds on [SABRE](https://github.com/UMass-LIDS/sabre) by Kevin Spiteri, Ramesh Sitaraman, and Daniel Sparacio (MMSys '18).
