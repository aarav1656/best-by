#!/bin/bash
cd "$(dirname "$0")/.."
export AWS_PROFILE=palimpsest AWS_DEFAULT_REGION=us-east-1
unset AWS_BEARER_TOKEN_BEDROCK
echo '$ aws s3 cp s3://bestby-evidence-.../F-0617-2025.txt -'
echo
aws s3 cp s3://bestby-evidence-079415246611/riverbend-dayton/2026/09/14/F-0617-2025.txt - 2>/dev/null | sed -n '43,57p'
