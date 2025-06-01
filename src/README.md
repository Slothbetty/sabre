# Step to generate graphs
## Generate network.json
Run network_generator.py to generate network.json by following command
`python network_generator.py -ne 10 -d 4000 -bm 3000 -bs 1500 -lm 150 -ls 50`
## Generate graphs for abrs.
Update the abrArray in run_all.py to choose abr algorithms.
Run run_all.py to generate graphs for abrs
`python run_all.py`
## Run Multiple Seek command
Create a multiple seek config as following:
`{
  "seeks": [
    {"seek_when": 15, "seek_to": 18},
    {"seek_when": 40, "seek_to": 43}
  ]
}
`
Run following command to see multiple seek result
`python sabre.py -v -sc seeks.json`