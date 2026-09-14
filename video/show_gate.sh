#!/bin/bash
cd "$(dirname "$0")/.."
echo '$ # from the pass that just ran, with nobody watching'
grep -E '"event": "(case_opened|notice_drafted|awaiting_approval|pulled|record_filed)"' /tmp/bestby_agent_pass.log \
  | grep -E 'b602180ab006f38b|73a4bb419a7da04b' | head -6 | cut -c1-118
echo
echo '$ # the pull happened. the record was filed. nobody was emailed.'
