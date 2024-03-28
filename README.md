# AWS Accounts To CSV

This project consists of a Python script that uses Boto3 to interact with AWS Organizations. It fetches a list of all AWS accounts under the organization, including details such as account name, ID, organizational unit (OU) paths, email, status, and join method. The results are output to a CSV file.

## Getting Started

These instructions will guide you through setting up and running the project on your local machine using Docker and Docker Compose.

### Prerequisites

- Docker
- Docker Compose
- AWS CLI (optional, for configuring AWS credentials)

### AWS Credentials

Before running the script, you must have your AWS credentials configured. This can be done in several ways:

1. **AWS CLI:** If you have the AWS CLI installed, configure your credentials using `aws configure`.
2. **Environment Variables:** Set your AWS credentials as environment variables in the `docker-compose.yml` file.

### Configuring the Project

1. Clone this repository to your local machine.
2. Navigate to the project directory.
3. Ensure your AWS credentials are correctly set like this:

```
export AWS_ACCESS_KEY_ID=$YOUR_AWS_ACCESS_KEY_ID
export AWS_SECRET_ACCESS_KEY=$YOUR_AWS_SECRET_ACCESS_KEY
export AWS_DEFAULT_REGION=$YOUR_AWS_DEFAULT_REGION
```

### How to output csv

```
# 
docker-compose up
```

### Option

If you want to output ID store information (users, groups), permission sets, and assignment information as a Markdown file, run the following command.

```
docker compose run aws-org-script python summarize.py
```