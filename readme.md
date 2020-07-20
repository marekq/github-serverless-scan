github-serverless-scan
======================

Scan your GitHub repositories with CloudFormation or AWS SAM code with cfn-lint. The stack deploys two Lambda functions and a DynamoDB table as shown below. 


![alt text](./docs/architecture.png)


- The "scan-lambda" function retrieves the user's GitHub repositories and sends them to SQS. 
- The SQS queue triggers the "lint-lambda" function which runs cfn-lint and a few keyword checks on the repo. 
- The results of the scan are stored in a DynamoDB table, which makes it easier to export or process the scan results. 


Installation
------------

Run 'sam build' and 'sam deploy -g' in the root of the directory to deploy the stack. The neccesary infrastructure and dependancies will be built and provisioned automatically. 


Roadmap
-------

- [ ] Add CDK support if this is feasible to run in Lambda in order to run 'cdk synth' to generate CloudFormation output. This would allow CDK repo's to be scanned for misconfigurations as well. 
- [ ] Add more intelligent retrieval of feature branches, right now only the main one is downloaded.
- [ ] Add other security infrastructure as code scanning software, such as Checkov. 
- [ ] Convert the SQS setup to Step Functions, in order to provide more powerful scanning patterns and better debugging of scan results. 
- [ ] Create an easy export function to generate reports (i.e. as a CSV file or as a CloudWatch/QuickSight dashboard). 


Contact
-------

In case you have any suggestions, questions or remarks, please raise an issue or reach out to @marekq.
