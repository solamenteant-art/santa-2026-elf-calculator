#!/bin/bash
# Elf Calculator - EC2 proof-burst bootstrap.
# Paste this whole script into the "User data" box when launching the
# instance, after replacing PASTE_TOKEN_HERE with the fine-grained
# GitHub token (this repo only, Contents = Read and write, 7-day expiry).
# The instance clones the solver, grinds one shard, pushes the results
# back to the repo's "shards" branch, and shuts itself down.
export GITHUB_PAT="PASTE_TOKEN_HERE"
export START=0
export END=100
export K=10
export SEED_BASE=7000000
export MIN_LEN=400
export PAR=4
exec > /var/log/elf-burst.log 2>&1
set -x
apt-get update -y
apt-get install -y git python3
git clone https://github.com/solamenteant-art/santa-2026-elf-calculator.git /opt/elf
bash /opt/elf/aws/run_shard.sh
shutdown -h now
