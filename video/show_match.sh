#!/bin/bash
cd "$(dirname "$0")/.."
echo '$ curl "https://api.fda.gov/food/enforcement.json?search=recall_number:%22F-0617-2025%22"'
echo
echo '  recalling_firm, status, classification:'
curl -s "https://api.fda.gov/food/enforcement.json?search=recall_number:%22F-0617-2025%22" \
  | .venv/bin/python -c "
import json,sys
r = json.load(sys.stdin)['results'][0]
print('   ', r['recalling_firm'][:64])
print('   ', r['status'], '/', r['classification'])
print()
print('  the entire string the firm published to identify affected units:')
print('   ', repr(r['code_info']))
"
echo
echo '$ # what agent/feeds/openfda.py pulls out of that free text'
.venv/bin/python -c "
from datetime import date
from agent.feeds.openfda import fetch
r = [x for x in fetch(date(2025,1,1)) if x.recall_number == 'F-0617-2025'][0]
c = r.identifiers
print('    lot_codes      ', c.lot_codes)
print('    best_by_dates  ', c.best_by_dates)
print('    upcs           ', c.upcs)
"
