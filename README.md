Architecture (high-level) 

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
How it works

You run the local CLI with one or more .pdf / .docx files.

The CLI uploads each file to S3 input/.

S3 fires an ObjectCreated event (filtered to input/) which triggers the Lambda function.

Lambda downloads the uploaded object to /tmp, runs Docling conversion, and writes the result to S3 output/ as a .md file.

The CLI polls S3 output/ until the .md exists, then downloads it to your local folder.

Errors are logged to CloudWatch Logs, and an optional *.error.txt is written to output/ when conversion fails.

Deployment instructions
Prerequisites

AWS account (Region: us-east-2)

AWS CLI configured: aws configure

Docker Desktop installed and running

Git (for GitHub submission)

Python 3.11+ (you have Python 3.14)

1) Configure AWS region
aws configure set region us-east-2

2) Build & push the Lambda container image to ECR

Set variables (PowerShell):

$REGION="us-east-2"
$ECR_REPO="docling-converter"
$IMAGE_TAG="v3"   # use your latest working tag

$ACCOUNT_ID=(aws sts get-caller-identity --query Account --output text)
$ECR_URI="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$ECR_REPO"


Create ECR repo (only once):

aws ecr create-repository --repository-name $ECR_REPO --region $REGION


Login Docker to ECR:

aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"


Build (linux/amd64) and push:

docker buildx build --platform linux/amd64 --provenance=false --sbom=false --load -t "${ECR_REPO}:${IMAGE_TAG}" .\lambda
docker tag "${ECR_REPO}:${IMAGE_TAG}" "${ECR_URI}:${IMAGE_TAG}"
docker push "${ECR_URI}:${IMAGE_TAG}"

3) Deploy CloudFormation stack

Choose a globally-unique bucket name:

$STACK_NAME="docling-stack-4"
$BUCKET_NAME="docling-converter-<yourname>-$(Get-Random -Minimum 10000000 -Maximum 99999999)"


Deploy:

aws cloudformation deploy --region $REGION --stack-name $STACK_NAME --template-file infra/docling-stack.yaml --capabilities CAPABILITY_NAMED_IAM --parameter-overrides BucketName=$BUCKET_NAME EcrRepoName=$ECR_REPO ImageTag=$IMAGE_TAG


Verify outputs:

aws cloudformation describe-stacks --region $REGION --stack-name $STACK_NAME --query "Stacks[0].Outputs" --output table

Usage examples
1) Upload files directly with AWS CLI (quick test)

From the project root (where your files are):

aws s3 cp .\sample.docx "s3://$BUCKET_NAME/input/sample.docx"
aws s3 cp .\sample.pdf  "s3://$BUCKET_NAME/input/sample.pdf"


Check results:

aws s3 ls "s3://$BUCKET_NAME/output/" --recursive


Download the Markdown:

aws s3 cp "s3://$BUCKET_NAME/output/sample.md" .\sample.md

2) Use the local CLI tool (required deliverable)

Install dependency:

pip install boto3


Run:

python .\cli\cloud_proc.py --bucket $BUCKET_NAME .\sample.pdf .\sample.docx


Expected:

Upload messages

“waiting / polling” progress

.md downloaded locally

.md stored in s3://<bucket>/output/

Cost estimates for typical usage

This project uses AWS S3 + Lambda + CloudWatch Logs + ECR. Typical cost for a class project is low.

Typical “student usage” example

Assume:

~100 conversions/month

files are small (a few MB each)

Lambda runs up to a few minutes per document

logs are moderate

S3: very low (pennies). Storage and requests are inexpensive for small volumes.
Lambda: charged by execution time + memory. With 3008–4096 MB and longer conversions, the cost could be noticeable but still typically small at student scale.
CloudWatch Logs: small, but can grow if you log lots of text.
ECR: stores image layers. Usually small unless you push many tags.

In practice, for a small class workload, this is usually well under a few dollars/month, often close to $0–$2 depending on runtime and how many times you rebuild/push images.

(You can include your actual bill screenshot if your instructor allows.)

Limitations and potential improvements
Limitations

Large PDFs may exceed Lambda time/memory limits (900s max timeout).

Some PDF conversions require system libraries (example: libGL.so.1), which must be included in the container image.

Cold starts may be slower because Docling + dependencies are large.

Conversion quality depends on document complexity (tables, scans, unusual fonts).

Current design is synchronous “polling” from CLI; many files may take time.

Potential improvements (realistic and low-risk)

Better status tracking: write a small JSON status file to output/ like output/<name>.status.json (processing/success/error).

More robust naming: include a UUID in output names to avoid collisions.

Retries & backoff in CLI: exponential backoff and a max wait time.

SNS notification: publish completion messages to SNS so you don’t need polling.

Optional DynamoDB job table: store job status + timestamps (still simple).

Compression: gzip markdown before storing for large outputs.

Security hardening: block public access on S3, enable bucket encryption, add lifecycle policy to expire old input/output files.
