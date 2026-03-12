#!/bin/bash

DATASET="eval/prompts.jsonl"

echo "Running benchmark with 10 prompts..."
python benchmark_runner.py --dataset $DATASET --batch-size 10

echo "Running benchmark with 50 prompts..."
python benchmark_runner.py --dataset $DATASET --batch-size 50

echo "Running benchmark with 100 prompts..."
python benchmark_runner.py --dataset $DATASET --batch-size 100

echo "Running benchmark with 200 prompts..."
python benchmark_runner.py --dataset $DATASET --batch-size 200

