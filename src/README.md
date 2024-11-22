# Step to generate graphs
## Generate network.json
Run network_generator.py to generate network.json by following command
`python network_generator.py -ne 10 -d 4000 -bm 3000 -bs 1500 -lm 150 -ls 50`
## Generate graphs for abrs.
Update the abrArray in run_all.py to choose abr algorithms.
Run run_all.py to generate graphs for abrs
`python run_all.py`
