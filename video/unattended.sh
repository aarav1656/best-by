#!/bin/bash
# Production, with nobody watching.
cd "$(dirname "$0")/.."
export AWS_PROFILE=palimpsest AWS_DEFAULT_REGION=us-east-1
unset AWS_BEARER_TOKEN_BEDROCK
echo '$ aws scheduler list-schedules'
aws scheduler list-schedules --query 'Schedules[?contains(Name,`bestby`)].[Name,State]' --output text
echo
echo '$ aws lambda invoke --function-name bestby-run'
aws lambda invoke --function-name bestby-run --payload '{}' --cli-binary-format raw-in-base64-out \
  --cli-read-timeout 300 /tmp/bb.json >/dev/null 2>&1
.venv/bin/python -c "
import json
d = json.load(open('/tmp/bb.json'))
for k in ['lots_checked','units_on_shelf','units_distributed','recalls_considered','interruptions','cases_to_pull','households_to_notify','lots_cleared_by_code','source','seconds']:
    if k in d: print(f'  {k:22} {d[k]}')
"
echo
echo '$ aws s3 ls s3://bestby-evidence-079415246611/riverbend-dayton/ --recursive | tail -3'
aws s3 ls s3://bestby-evidence-079415246611/riverbend-dayton/ --recursive 2>/dev/null | tail -3
