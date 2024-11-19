import subprocess
import argparse

def run_scripts(abr):
    try:
        # Run extract_data.py
        subprocess.run(['python', 'extract_data.py', '-a', abr], check=True)
        
        # Run graph_generate.py with -a <abr> argument
        subprocess.run(['python', 'graph_generate.py', '-a', abr], check=True)
        
        print("All scripts executed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"An error occurred while running scripts: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run all scripts with specified ABR algorithm')
    parser.add_argument('-a', '--abr', type=str, required=True, help='ABR algorithm to use')
    args = parser.parse_args()
    
    run_scripts(args.abr)