#!/bin/bash

# set cli color variables
RED='\033[0;31m'
NC='\033[0m'

# build the lambda package in a docker container
sam build -u

# validate the sam stack
echo -e "\n${RED} * running sam validate and cfn-lint locally to test cloudformation template... ${NC}\n"
sam validate

# deploy the sam stack to the aws region
echo -e "\n${RED} * deploying the SAM stack to aws... ${NC}\n"

# check if samconfig.toml file is present
if [ ! -f samconfig.toml ]; then
    echo "no samconfig.toml found, starting guided deploy"
    sam deploy -g
else
    echo "samconfig.toml found, proceeding to deploy"
    sam deploy
fi
