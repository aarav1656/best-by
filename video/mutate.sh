#!/bin/bash
# Break the guardrail on purpose, watch the suite go red, put it back.
cd "$(dirname "$0")/.."
cp agent/bestby_agent.py /tmp/bestby_veto.bak
.venv/bin/python - <<'PY'
import pathlib
p = pathlib.Path('agent/bestby_agent.py')
s = p.read_text()
s = s.replace('''        if event.tool_use.get("name") != "notify_households":
            return''', '''        if event.tool_use.get("name") != "notify_households":
            return
        return''', 1)
p.write_text(s)
PY
echo '$ # NotifyVeto.inspect now returns before it can refuse anything'
.venv/bin/python -m pytest tests/test_veto.py -q 2>&1 | tail -5
cp /tmp/bestby_veto.bak agent/bestby_agent.py
echo
echo '$ # restored'
.venv/bin/python -m pytest tests -q 2>&1 | tail -2
