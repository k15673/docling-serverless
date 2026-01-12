# Docling Serverless -- PDF / DOCX to Markdown {#docling-serverless-pdf-docx-to-markdown}

**Course:** COMP490  
**Project Type:** Serverless Document Processing Pipeline

This project implements a **serverless workflow on AWS** that converts
**PDF and DOCX documents into Markdown** using **Docling**. A local CLI
uploads documents to Amazon S3, an AWS Lambda function processes them,
and the resulting Markdown files are downloaded back to the local
machine.

## High‑Level Architecture

    +--------------------+         upload            +---------------------------+
    | Local CLI tool     |  ---------------------->  | S3 Bucket                 |
    | (cli/cloud_proc.py)|                           |  input/  output/          |
    +--------------------+                           +------------+--------------+
                                                                 |
                                                                 | S3:ObjectCreated (prefix=input/)
                                                                 v
                                                       +---------------------------+
                                                       | AWS Lambda (Container)    |
                                                       | Docling converts to MD    |
                                                       +------------+--------------+
                                                                    |
                                                                    | PutObject to output/
                                                                    v
                                                       +---------------------------+
                                                       | S3 Bucket output/         |
                                                       | *.md + optional *.error   |
                                                       +---------------------------+
                                                                 ^
                                                                 |
                                            poll & download       |
    +--------------------+  <-------------------------------------+
    | Local CLI tool     |
    +--------------------+

## How It Works

1.  If we run the **local CLI** with one or more `.pdf` or `.docx`
    files.
2.  The CLI uploads each file to the S3 bucket under the `input/`
    prefix.
3.  An **S3 ObjectCreated event** triggers the AWS Lambda function.
4.  Lambda downloads the file to `/tmp`, runs **Docling** to convert it
    to Markdown, and uploads the result to `output/`.
5.  The CLI **polls the output bucket** until the `.md` file appears,
    then downloads it locally.
6.  Errors are logged to **CloudWatch Logs**, and an optional
    `*.error.txt` file is written to `output/` if conversion fails.

## Deployment Instructions

### Prerequisites

- AWS account (Region: `us-east-2`)
- AWS CLI configured (`aws configure`)
- Docker Desktop installed and running
- Git
- Python **3.11+**

###  1.Configure AWS Region {#configure-aws-region}

    aws configure set region us-east-2

### 2.Build & Push the Lambda Container Image (ECR) {#build-push-the-lambda-container-image-ecr}

#### Set variables (PowerShell)

    $REGION="us-east-2"
    $ECR_REPO="docling-converter"
    $IMAGE_TAG="v3"   # use your latest working tag

    $ACCOUNT_ID=(aws sts get-caller-identity --query Account --output text)
    $ECR_URI="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$ECR_REPO"

#### Create the ECR repository (only once)

    aws ecr create-repository --repository-name $ECR_REPO --region $REGION

#### Login Docker to ECR

    aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"

#### Build and push the image

    docker buildx build --platform linux/amd64 --provenance=false --sbom=false --load -t "${ECR_REPO}:${IMAGE_TAG}" .\lambda
    docker tag "${ECR_REPO}:${IMAGE_TAG}" "${ECR_URI}:${IMAGE_TAG}"
    docker push "${ECR_URI}:${IMAGE_TAG}"

### 3 Deploy the CloudFormation Stack {#deploy-the-cloudformation-stack}

Choose a globally unique bucket name:

    $STACK_NAME="docling-stack-4"
    $BUCKET_NAME="docling-converter-<yourname>-$(Get-Random -Minimum 10000000 -Maximum 99999999)"

Deploy:

    aws cloudformation deploy \
      --region $REGION \
      --stack-name $STACK_NAME \
      --template-file infra/docling-stack.yaml \
      --capabilities CAPABILITY_NAMED_IAM \
      --parameter-overrides BucketName=$BUCKET_NAME EcrRepoName=$ECR_REPO ImageTag=$IMAGE_TAG

Verify outputs:

    aws cloudformation describe-stacks --region $REGION --stack-name $STACK_NAME --query "Stacks[0].Outputs" --output table

## Usage Examples

### Option 1: Upload Files Directly with AWS CLI (Quick Test)

    aws s3 cp .\sample.docx "s3://$BUCKET_NAME/input/sample.docx"
    aws s3 cp .\sample.pdf  "s3://$BUCKET_NAME/input/sample.pdf"

Check results:

    aws s3 ls "s3://$BUCKET_NAME/output/" --recursive

Download the Markdown:

    aws s3 cp "s3://$BUCKET_NAME/output/sample.md" .\sample.md

### Option 2: Use the Local CLI Tool (Required Deliverable)

Install dependency:

    pip install boto3

Run:

    python .\cli\cloud_proc.py --bucket $BUCKET_NAME .\sample.pdf .\sample.docx

Expected behavior:

- Upload progress messages
- Polling / waiting output
- `.md` files downloaded locally
- `.md` files stored in `s3://<bucket>/output/`

## Cost Estimates (Typical Student Usage)

This project uses **AWS S3, Lambda, CloudWatch Logs, and ECR**.

**Example usage:**

- \~100 conversions per month
- Small files (a few MB each)
- Lambda runs for up to a few minutes per document

**Estimated cost:**

- **S3:** pennies for storage and requests
- **Lambda:** small cost based on runtime and memory (typically low at
  student scale)
- **CloudWatch Logs:** minimal unless excessive logging
- **ECR:** minimal unless pushing many image tags

For a class project, total cost is typically **\$0--\$2/month**.

## Limitations

- Large PDFs may exceed Lambda timeout limits (900 seconds max).
- Some document conversions require additional system libraries (e.g.,
  `libGL.so.1`).
- Cold starts can be slow due to large dependencies.
- Conversion quality varies with document complexity.
- CLI currently relies on synchronous polling.

## Potential Improvements

- Adding structured job status files (JSON) in `output/`
- Include UUIDs in filenames to avoid collisions
- Exponential backoff and max wait time in CLI polling
- SNS notifications instead of polling
- Optional DynamoDB job status table
- Lifecycle policies to auto‑expire old S3 files
- Improved security (encryption, stricter IAM policies)

## Summary

This project demonstrates a **realistic serverless architecture** for
document processing using AWS services and modern containerized Lambda
functions. It is designed to be simple, cost‑effective, and suitable for
academic use while remaining extensible for future enhancements.
