#!/bin/bash

# set cli color variables
RED='\033[0;31m'
BLACK='\033[0m'

# validate the sam stack
echo -e "\n${RED} * running sam validate and cfn-lint locally to test cloudformation template... ${BLACK}\n"
sam validate

# build the lambda package in a docker container
echo -e "\n${RED} * building sam template... ${BLACK}\n"
sam build --use-container 

# deploy the sam stack to the aws region
echo -e "\n${RED} * deploying the sam stack to aws... ${BLACK}\n"

# check if samconfig.toml file is present
if [ ! -f samconfig.toml ]; then
    echo "no samconfig.toml found, starting guided deploy"
    sam deploy -g
else
    echo "samconfig.toml found, proceeding to deploy"
    sam deploy
fi
