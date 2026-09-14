#!/usr/bin/env bash
# Deploys the bestby-run Lambda: its own least-privilege execution role, a
# packaged zip, the function, and two EventBridge schedules. Safe to re-run;
# every step either overwrites the same-named resource or checks for it first.
set -euo pipefail

export AWS_PROFILE=${AWS_PROFILE:-palimpsest}
export AWS_DEFAULT_REGION=us-east-1
unset AWS_BEARER_TOKEN_BEDROCK || true

REGION=us-east-1
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
FUNCTION_NAME=bestby-run
ROLE_NAME=bestby-exec
ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"
SCHEDULER_ROLE_NAME=bestby-scheduler
SCHEDULER_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${SCHEDULER_ROLE_NAME}"
TABLE_CASES=bestby-cases
TABLE_RECALLS=bestby-recalls
BUCKET=bestby-evidence-${ACCOUNT_ID}
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${REPO_ROOT}/build"
ZIP_PATH="${REPO_ROOT}/build.zip"

echo "== account ${ACCOUNT_ID} region ${REGION} =="

echo "== execution role ${ROLE_NAME} =="
if ! aws iam get-role --role-name "${ROLE_NAME}" >/dev/null 2>&1; then
  aws iam create-role --role-name "${ROLE_NAME}" --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [
      {"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}
    ]
  }' >/dev/null
  echo "waiting for the new IAM role to propagate..."
  sleep 10
fi

aws iam put-role-policy --role-name "${ROLE_NAME}" --policy-name bestby-dynamodb --policy-document '{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "BestByTables",
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem",
        "dynamodb:Query", "dynamodb:BatchWriteItem", "dynamodb:BatchGetItem"
      ],
      "Resource": [
        "arn:aws:dynamodb:'"${REGION}"':'"${ACCOUNT_ID}"':table/'"${TABLE_CASES}"'",
        "arn:aws:dynamodb:'"${REGION}"':'"${ACCOUNT_ID}"':table/'"${TABLE_RECALLS}"'"
      ]
    }
  ]
}'

aws iam put-role-policy --role-name "${ROLE_NAME}" --policy-name bestby-s3-evidence --policy-document '{
  "Version": "2012-10-17",
  "Statement": [
    {"Sid": "BestByEvidenceList", "Effect": "Allow", "Action": ["s3:ListBucket"],
     "Resource": "arn:aws:s3:::'"${BUCKET}"'"},
    {"Sid": "BestByEvidenceObjects", "Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject"],
     "Resource": "arn:aws:s3:::'"${BUCKET}"'/*"}
  ]
}'

# The log group name is fixed by the function name, but CloudWatch requires the
# log stream segment of the ARN to stay wildcarded, because Lambda names streams
# per invocation. That one wildcard is unavoidable.
aws iam put-role-policy --role-name "${ROLE_NAME}" --policy-name bestby-logs --policy-document '{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "BestByLogs",
      "Effect": "Allow",
      "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
      "Resource": "arn:aws:logs:'"${REGION}"':'"${ACCOUNT_ID}"':log-group:/aws/lambda/'"${FUNCTION_NAME}"':*"
    }
  ]
}'

# ses:SendEmail has no per-recipient resource to scope to. identity/* is the
# tightest ARN pattern SES accepts: it means "send as an identity in this
# account", not "any SES action anywhere".
#
# ListEmailIdentities is account-level and does not support resource-level
# permissions, so scoping it to identity/* silently denies it. That is not a
# theoretical nit: agent/dispatch.py calls it to decide whether SES in sandbox
# will accept a household's real address or whether the notice has to be routed
# to the mailbox simulator, so the denial surfaced as "the household
# notification encountered a permission issue" on a case the coordinator had
# already approved. It gets its own statement on "*".
aws iam put-role-policy --role-name "${ROLE_NAME}" --policy-name bestby-ses --policy-document '{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "BestByHouseholdNotices",
      "Effect": "Allow",
      "Action": ["ses:SendEmail"],
      "Resource": "arn:aws:ses:'"${REGION}"':'"${ACCOUNT_ID}"':identity/*"
    },
    {
      "Sid": "BestByCheckDeliverability",
      "Effect": "Allow",
      "Action": ["ses:ListEmailIdentities"],
      "Resource": "*"
    }
  ]
}'

echo "== scheduler invoke role =="
if ! aws iam get-role --role-name "${SCHEDULER_ROLE_NAME}" >/dev/null 2>&1; then
  aws iam create-role --role-name "${SCHEDULER_ROLE_NAME}" --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [
      {"Effect": "Allow", "Principal": {"Service": "scheduler.amazonaws.com"}, "Action": "sts:AssumeRole"}
    ]
  }' >/dev/null
  echo "waiting for the new IAM role to propagate..."
  sleep 10
fi
aws iam put-role-policy --role-name "${SCHEDULER_ROLE_NAME}" --policy-name bestby-invoke-lambda --policy-document '{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "InvokeBestByRun",
      "Effect": "Allow",
      "Action": "lambda:InvokeFunction",
      "Resource": "arn:aws:lambda:'"${REGION}"':'"${ACCOUNT_ID}"':function:'"${FUNCTION_NAME}"'"
    }
  ]
}'

# The Anthropic key is read from the .env the user placed, passed straight into
# the function configuration, and never printed. Without it the scheduled pass
# still runs, on the deterministic matcher alone, with no identity reading.
LAMBDA_ENV="BESTBY_SENDER=bestby@getava.xyz"
if [ -f "${REPO_ROOT}/.env" ]; then
  ANTHROPIC_KEY="$(grep -m1 '^ANTHROPIC_API_KEY=' "${REPO_ROOT}/.env" | cut -d= -f2- | tr -d '"'"'"'\r')"
  if [ -n "${ANTHROPIC_KEY}" ]; then
    LAMBDA_ENV="${LAMBDA_ENV},ANTHROPIC_API_KEY=${ANTHROPIC_KEY}"
    echo "== anthropic key found in .env, the scheduled pass can read identity =="
  fi
else
  echo "== no .env, the scheduled pass will run deterministic matching only =="
fi

echo "== packaging =="
rm -rf "${BUILD_DIR}" "${ZIP_PATH}"
mkdir -p "${BUILD_DIR}"
# boto3 ships in the python3.12 Lambda runtime. Everything else the unattended
# run needs is vendored, including strands and anthropic, because the scheduled
# pass runs the same agent a person runs locally.
# Built on macOS, run on Amazon Linux: pydantic-core and friends ship compiled
# extensions, so without the explicit platform pins the function dies at import
# with "No module named pydantic_core._pydantic_core".
"${REPO_ROOT}/.venv/bin/pip" install --target "${BUILD_DIR}" \
  --platform manylinux2014_x86_64 --implementation cp --python-version 3.12 \
  --only-binary=:all: --upgrade \
  httpx strands-agents anthropic --quiet --disable-pip-version-check
find "${BUILD_DIR}" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
# dist-info stays: anthropic resolves its own dependency versions through
# importlib.metadata at import time, so stripping metadata to save a few MB
# kills the function with PackageNotFoundError instead.
cp -R "${REPO_ROOT}/agent" "${BUILD_DIR}/agent"
find "${BUILD_DIR}/agent" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
cp "${REPO_ROOT}/infra/lambda_handler.py" "${BUILD_DIR}/lambda_handler.py"
# Only the intake log is needed in the zip. The multi-MB captured feed dump in
# data/ is for the offline test suite; the Lambda always fetches openFDA live.
mkdir -p "${BUILD_DIR}/data"
cp "${REPO_ROOT}/data/pantry.json" "${BUILD_DIR}/data/pantry.json"
( cd "${BUILD_DIR}" && zip -r -q "${ZIP_PATH}" . -x '*.pyc' )
echo "package: ${ZIP_PATH} ($(du -h "${ZIP_PATH}" | cut -f1))"

echo "== deploying ${FUNCTION_NAME} =="
if aws lambda get-function --function-name "${FUNCTION_NAME}" >/dev/null 2>&1; then
  aws lambda update-function-code --function-name "${FUNCTION_NAME}" --zip-file "fileb://${ZIP_PATH}" >/dev/null
  aws lambda wait function-updated --function-name "${FUNCTION_NAME}"
  aws lambda update-function-configuration \
    --function-name "${FUNCTION_NAME}" --role "${ROLE_ARN}" --runtime python3.12 \
    --handler lambda_handler.handler --timeout 900 --memory-size 512 \
    --environment "Variables={${LAMBDA_ENV}}" >/dev/null
  aws lambda wait function-updated --function-name "${FUNCTION_NAME}"
else
  aws lambda create-function \
    --function-name "${FUNCTION_NAME}" --runtime python3.12 --role "${ROLE_ARN}" \
    --handler lambda_handler.handler --timeout 900 --memory-size 512 \
    --environment "Variables={${LAMBDA_ENV}}" --zip-file "fileb://${ZIP_PATH}" >/dev/null
  aws lambda wait function-active --function-name "${FUNCTION_NAME}"
fi

echo "== schedules =="
LAMBDA_ARN=$(aws lambda get-function --function-name "${FUNCTION_NAME}" --query 'Configuration.FunctionArn' --output text)

create_or_update_schedule() {
  local name="$1" expr="$2" state="$3" payload="$4"
  local target='{"Arn":"'"${LAMBDA_ARN}"'","RoleArn":"'"${SCHEDULER_ROLE_ARN}"'","Input":"'"${payload}"'"}'
  if aws scheduler get-schedule --name "$name" >/dev/null 2>&1; then
    aws scheduler update-schedule --name "$name" --schedule-expression "$expr" --state "$state" \
      --flexible-time-window '{"Mode":"OFF"}' --target "$target" >/dev/null
  else
    aws scheduler create-schedule --name "$name" --schedule-expression "$expr" --state "$state" \
      --flexible-time-window '{"Mode":"OFF"}' --target "$target" >/dev/null
  fi
  echo "  ${name}: ${expr} [${state}]"
}

# A pantry's recall check belongs before the doors open, not at midnight UTC.
# 11:00 UTC is 07:00 in Dayton, which is when the coordinator arrives and an
# hour before the first distribution shift.
create_or_update_schedule bestby-daily "cron(0 11 * * ? *)" ENABLED '{\"agent\":true}'
# Created disabled. Flip it on to watch the unattended loop run without waiting
# a day for it.
create_or_update_schedule bestby-frequent "rate(15 minutes)" DISABLED '{\"agent\":true}'

echo ""
echo "deployed: ${FUNCTION_NAME}"
echo "invoke:   aws lambda invoke --function-name ${FUNCTION_NAME} --payload '{\"agent\":true}' --cli-binary-format raw-in-base64-out /dev/stdout"
echo "logs:     aws logs tail /aws/lambda/${FUNCTION_NAME} --follow"
