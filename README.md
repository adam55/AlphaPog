### API to query data from the RIOT API.
It was essentially a quick exercise to use CodeBuild and CodePipeline.
- Deployed using Chalice.
- Hosted on AWS Lambda.
- CI/CD set up with CodeBuild, CloudFormation and CodePipeline.
- The API can be queried to obtain data from the game TFT.
- There is a cron job set up to save some data about top 200 players to a DynamoDB database.

