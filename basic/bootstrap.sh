#!/usr/bin/env bash


python fetch_creds.py
source tackerc
python create_endpoints.py
python create_chains.py
