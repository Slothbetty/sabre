import subprocess
import csv
import argparse

# Function to run sabre.py with the `-g` argument and capture its output
def capture_print_output(abr):
    # Run sabre.py with the `-g` argument and capture the output
    result = subprocess.run(['python', 'sabre.py', '-g','-a', abr, '-sc', 'seeks.json'], capture_output=True, text=True)
    # Split the output into lines
    return result.stdout.splitlines()

# Function to parse each line into a dictionary
def parse_line(line):
    fields = line.split()
    # Filter out invalid fields that don’t contain '='
    valid_fields = [field for field in fields if '=' in field]
    return {field.split('=')[0]: field.split('=')[1] for field in valid_fields}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate graph with specified ABR algorithm')
    parser.add_argument('-a', '--abr', type=str, required=True, help='ABR algorithm to use')
    args = parser.parse_args()
    
    # Capture the printed data
    data = capture_print_output(args.abr)
    # Filter out any empty lines or lines that are not properly formatted
    parsed_data = [parse_line(line) for line in data if line.strip() and '=' in line]

    # Ensure there is data to write
    if parsed_data:
        # Get the header from the keys of the first dictionary
        header = parsed_data[0].keys()

        # Write to a CSV file
        with open(f'{args.abr}.csv', 'w', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=header)
            writer.writeheader()
            writer.writerows(parsed_data)

        print(f"Data successfully written to {args.abr}.csv")
    else:
        print("No valid data found to write to CSV.")
    