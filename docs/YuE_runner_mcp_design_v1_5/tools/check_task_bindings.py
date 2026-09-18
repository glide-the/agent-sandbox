#!/usr/bin/env python3
"""Validate v1.5 documentation examples, not a live service or model."""
from __future__ import annotations
from pathlib import Path
import copy
import json
import re
import sys
import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    'yue2_task': ('yue2_processor', 'YuE2', '/root/yue-env'),
    'sheetsage2_task': ('sheetsage2_processor', 'SheetSage2', '/root/sheetsage2-env'),
}

def check() -> dict:
    cfg = yaml.safe_load((ROOT / 'examples/sandbox.music.example.yaml').read_text())
    assert isinstance(cfg['preprocess'], list)
    assert isinstance(cfg['tasks'], list)
    processors = {k: v for item in cfg['preprocess'] for k, v in item.items()}
    tasks = {k: v for item in cfg['tasks'] for k, v in item.items()}
    assert set(tasks) == set(EXPECTED), 'Unexpected task registration'
    for name, (processor, processor_type, env) in EXPECTED.items():
        task = tasks[name]
        assert task['name'] == name
        assert len(task['preprocess']) == 1, 'A task may not select another model'
        binding = next(iter(task['preprocess'][0].values()))
        assert binding == {'processor': processor, 'processor_name': processor_type}
        assert processors[processor]['name'] == processor
        assert processors[processor]['environment'] == env
    assert len({p['environment'] for p in processors.values()}) == len(processors)
    schema = json.loads((ROOT / 'examples/submission.schema.json').read_text())
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    positives = []
    negatives = []
    for path in sorted((ROOT / 'examples').glob('*.submit.json')):
        data = json.loads(path.read_text())
        validator.validate(data)
        positives.append(path.name)
        wrong = copy.deepcopy(data)
        wrong['parameter']['task_name'] = (
            'yue2_task' if data['parameter']['task_name'] == 'sheetsage2_task' else 'sheetsage2_task'
        )
        assert not validator.is_valid(wrong), 'Cross-model combination was accepted'
        negatives.append('cross_model:' + path.name)
    sample = json.loads((ROOT / 'examples/01_generate.submit.json').read_text())
    for task_name in ('music_task', 'unknown_task'):
        wrong = copy.deepcopy(sample)
        wrong['parameter']['task_name'] = task_name
        assert not validator.is_valid(wrong)
        negatives.append('unregistered_task:' + task_name)
    for field in ('environment', 'processor', 'model_path'):
        wrong = copy.deepcopy(sample)
        wrong['payload'][field] = '/untrusted/path'
        assert not validator.is_valid(wrong)
        negatives.append('client_execution_field:' + field)
    for operation in ('plan', 'all_modes'):
        data = copy.deepcopy(sample)
        data['payload']['operation'] = operation
        validator.validate(data)
        positives.append('generated_fixture:' + operation)
    data = copy.deepcopy(sample)
    del data['payload']['request']
    data['payload'].update(operation='decode', source_task_id='existing_result_fixture')
    validator.validate(data)
    positives.append('generated_fixture:decode')
    diagrams = []
    for path in sorted((ROOT / 'diagrams').glob('*.mmd')):
        text = path.read_text()
        assert text.lstrip().startswith('sequenceDiagram')
        assert 'music_task' not in text
        stack=[]
        for line in text.splitlines():
            first=line.strip().split(' ',1)[0]
            if first in {'alt','loop','par','opt','critical','rect','break'}: stack.append(first)
            elif first == 'end':
                assert stack, f'Unbalanced end: {path.name}'
                stack.pop()
        assert not stack, f'Unclosed block: {path.name}'
        diagrams.append(path.name)
    return {
        'version':'1.5',
        'scope':'local documentation examples only',
        'passed':True,
        'model_bindings':EXPECTED,
        'positive_schema_cases':positives,
        'negative_schema_cases':negatives,
        'mermaid_structural_files':diagrams,
        'live_task_processor_environment_verified':False,
        'business_code_modified':False,
        'model_tests_run':False,
        'plugin_service_tests_run':False,
        'mermaid_parser_or_render_run':False,
    }

if __name__ == '__main__':
    try:
        report=check()
    except Exception as exc:
        print(f'FAIL: {type(exc).__name__}: {exc}', file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps(report,ensure_ascii=False,indent=2))
