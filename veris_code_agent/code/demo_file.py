"""
demo_file.py -- Gauntlet Code Analysis Demo

This file contains deliberate bugs for demo purposes.
The Code Analysis Agent must identify all of them.
"""

import os
import json


# BUG 1: Infinite loop -- while True with no break condition
def sync_database_records(records):
    index = 0
    while True:                          # Line 14: infinite loop -- no break
        record = records[index]
        print(f"Processing record: {record}")
        index += 1


# BUG 2: Off-by-one / unbounded index access
def get_last_three(items):
    result = []
    for i in range(len(items) + 1):      # Line 22: off-by-one, will raise IndexError
        result.append(items[i])
    return result


# BUG 3: Bare except swallowing all errors silently
def load_config(path):
    try:
        with open(path) as f:
            return json.load(f)
    except:                              # Line 31: bare except -- hides all errors
        pass


# BUG 4: Mutable default argument (classic Python gotcha)
def add_item(item, collection=[]):       # Line 35: mutable default argument
    collection.append(item)
    return collection


# BUG 5: Resource leak -- file opened but never closed
def read_log(filepath):
    f = open(filepath)                   # Line 41: file never closed, no context manager
    data = f.read()
    return data


# BUG 6: Recursive function with no base case
def countdown(n):
    print(n)
    countdown(n - 1)                     # Line 48: no base case, infinite recursion


# Clean function for contrast -- no bugs here
def calculate_average(numbers):
    if not numbers:
        return 0.0
    return sum(numbers) / len(numbers)


if __name__ == "__main__":
    # This will hit BUG 1 immediately
    sync_database_records([1, 2, 3])
