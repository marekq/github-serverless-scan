github-serverless-scan
======================

Scan your GitHub repositories with CloudFormation or AWS SAM code with cfn-lint. The stack deploys two Lambda functions, a Step Function, an S3 bucket and a DynamoDB table. You can invoke the scan using the Step Function which is provisioned. 

After a scan, you can review the results in the DynamoDB table. In addition, a CSV version of the scan output is stored on S3 for easier reviewing of results. Finally, you can select to optionally send an email with the results through SES.


![alt text](./docs/architecture.png)



Installation
------------

You need to have Docker, AWS SAM and cfn-lint installed on your machine. Next, run 'bash deploy.sh' in the root of the directory to deploy the stack. 

The neccesary infrastructure and dependancies will be built and provisioned automatically. In the output of the SAM template, you can find the name and direct URL to the Step Function that kicks off the scan for one Github profile. 

Within the Step Function input, configure the values as follows;

```
{
    "GithubRepo": "<github user (i.e. 'marekq')>",
    "ScanID": "<optional parameter - set a scan id for dynamodb results>
}
```


Roadmap
-------

- [ ] Add CDK support if this is feasible to run in Lambda in order to run 'cdk synth' to generate CloudFormation output. This would allow CDK repo's to be scanned for misconfigurations as well. 
- [ ] Add other security infrastructure as code scanning software, such as Checkov. 
- [ ] Add X-Ray support for the Step Function once it is available in AWS SAM. 
- [X] Create an easy export function to generate reports (i.e. as a CSV file or as a CloudWatch/QuickSight dashboard). 
- [X] Convert the SQS setup to Step Functions, in order to provide more powerful scanning patterns and better debugging of scan results. 
- [X] Add more intelligent retrieval of feature branches, right now only the main one is downloaded.
- [X] Add email sending of report results. 


Contact
-------

In case you have any suggestions, questions or remarks, please raise an issue or reach out to @marekq.
