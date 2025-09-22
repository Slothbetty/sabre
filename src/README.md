# Step to generate graphs
## Generate network.json
Run network_generator.py to generate network.json by following command
`python network_generator.py -ne 10 -d 4000 -bm 3000 -bs 1500 -lm 150 -ls 50`
## Generate graphs for abrs.
Update the abrArray in generate_abr_comparison.py to choose abr algorithms.
Run generate_abr_comparison.py to generate graphs for abrs
`python generate_abr_comparison.py`
## Run Multiple Seek command
Create a multiple seek config as following:
`{
  "seeks": [
    {"seek_when": 15, "seek_to": 18},
    {"seek_when": 40, "seek_to": 43}
  ]
}`
Run following command to see multiple seek result
`python sabre.py -v -sc seeks.json`

## Run with simulate_abr.py
Run sabre.py with verbose mode and save output to file:
```bash
python simulate_abr.py -o output.txt
```
With custom seek config:
```bash
python simulate_abr.py -o output.txt -s seeks.json
```

## Testing
### Regression Testing
Ensure simulation results remain consistent after code changes:

1. **Generate baseline results(Run Once):**
   ```bash
   python test_simulation.py --generate-baseline
   ```
   Remember to generate new baseline_simulation_results.txt whenever there are changes in movie.json, network.json or seeks.json.

2. **Run regression test:**
   ```bash
   python test_simulation.py
   ```

The test will compare current simulation results with the baseline and report any differences.