#!/usr/bin/env python3
import argparse
import json
import os
import sys

variant_values = [
    "sound",
    "vulnerable",
    "compilable",
    "uncompilable",
    "wrong",
    "wrong_format",
    "internal_tests_failure",
    "unknown_error",
    "no_patch",
]


def change_variant(input_file: str, cpv_name: str, new_variant: str) -> bool:
    """
    Change the variant value for a specific CPV name in a JSON result file.

    Args:
        input_file (str): Path to the input JSON file
        cpv_name (str): CPV name to find and update
        new_variant (str): New variant value to set

    Returns:
        bool: True if the CPV name was found and updated, False otherwise
    """
    if new_variant not in variant_values:
        raise ValueError(f"Invalid new variant: {new_variant}")

    try:
        # Read the input JSON file
        with open(input_file, "r") as f:
            data = json.load(f)

        # Check if the file has the expected structure
        if "results" not in data:
            print(f"Error: The JSON file {input_file} does not have a 'results' field")
            return False

        # Find and update the CPV name
        found = False
        for result in data["results"]:
            if result.get("cpv_name") == cpv_name:
                old_variant = result.get("variant", "unknown")
                result["variant"] = new_variant
                found = True
                print(f"Updated {cpv_name}: {old_variant} -> {new_variant}")
                break

        if not found:
            print(f"Error: CPV name '{cpv_name}' not found in the results")
            return False

        # Update statistics if they exist
        if "statistics" in data:
            # Create a dictionary to count variants
            variant_counts = {}
            for result in data["results"]:
                variant = result.get("variant")
                if variant:
                    variant_counts[variant] = variant_counts.get(variant, 0) + 1

            # Update statistics
            data["statistics"] = [
                [variant, count] for variant, count in variant_counts.items()
            ]

        # Write the updated data back to the file
        with open(input_file, "w") as f:
            json.dump(data, f, indent=2)

        print(f"Successfully updated {input_file}")
        return True

    except Exception as e:
        print(f"Error: {str(e)}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Change variant value for a specific CPV name in a JSON result file"
    )
    parser.add_argument("input_file", help="Path to the input JSON file")
    parser.add_argument("cpv_name", help="CPV name to find and update")
    parser.add_argument("new_variant", help="New variant value to set")

    args = parser.parse_args()

    # Check if the input file exists
    if not os.path.isfile(args.input_file):
        print(f"Error: The file {args.input_file} does not exist")
        sys.exit(1)

    # Change the variant
    success = change_variant(args.input_file, args.cpv_name, args.new_variant)

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
