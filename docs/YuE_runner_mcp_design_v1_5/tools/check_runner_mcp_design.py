#!/usr/bin/env python3
"""Validate documentation contracts only; no live MCP, HTTP, or model execution."""
from pathlib import Path, PurePosixPath, PureWindowsPath
import base64
import binascii
import copy
import hashlib
import json
import re
import sys
from urllib.parse import urlparse, parse_qs
import yaml
from jsonschema import Draft202012Validator
ROOT = Path(__file__).resolve().parents[1]

def validate_upload(a, schema):
    Draft202012Validator(schema).validate(a)
    path = PureWindowsPath(a['file_path']) if a['client_os']=='windows' else PurePosixPath(a['file_path'])
    if not path.is_absolute() or not path.name:
        raise ValueError('file_path must be absolute')
    return path.name

def check():
    count=0; rejected=0
    listing=json.loads((ROOT/'examples/mcp/tools.list.json').read_text())
    tools={x['name']:x for x in listing['result']['tools']}
    expected={'runner_upload','runner_submit','runner_result','runner_result_source'}
    assert set(tools)==expected
    for t in tools.values():Draft202012Validator.check_schema(t['inputSchema'])
    cfg=yaml.safe_load((ROOT/'examples/sandbox.mcp.example.yaml').read_text())
    assert set(cfg)=={'bootstrap'}
    m=cfg['bootstrap'][0]['runner_bootstrap_web']['mcp']
    assert m['path']=='/mcp' and set(m['tools'])==expected
    assert m['upload_capability_path']=='/api/uploads/{token}'
    assert m['upload_ttl_seconds']==300
    calls={}
    music=Draft202012Validator(json.loads((ROOT/'examples/submission.schema.json').read_text()))
    for p in sorted((ROOT/'examples/mcp').glob('*.call.json')):
        c=json.loads(p.read_text());assert c['method']=='tools/call'
        n=c['params']['name'];a=c['params']['arguments'];calls[n]=a
        Draft202012Validator(tools[n]['inputSchema']).validate(a);count+=1
        if n=='runner_submit':music.validate({'parameter':a['parameter'],'payload':a['payload']})
    assert set(calls)==expected
    assert validate_upload(calls['runner_upload'],tools['runner_upload']['inputSchema'])=='transfer-fixture.abc';count+=1
    raw=(ROOT/'examples/mcp/transfer-fixture.abc').read_bytes()
    inline=json.loads((ROOT/'examples/mcp/06_file_inline.result.json').read_text())['result']
    d=inline['structuredContent']['data']
    assert base64.b64decode(d['content_base64'],validate=True)==raw
    assert d['sha256']==hashlib.sha256(raw).hexdigest() and d['size_bytes']==len(raw)
    assert d['bytes_included'] is True and d['delivery']=='inline';count+=1
    upload=json.loads((ROOT/'examples/mcp/05_upload.result.json').read_text())['result']
    ud=upload['structuredContent']['data']
    assert ud['single_use'] and ud['expires_in_seconds']==300 and not ud['bytes_uploaded']
    assert '/api/uploads/' in ud['upload_url'] and 'curl ' in upload['content'][0]['text'];count+=1
    link=json.loads((ROOT/'examples/mcp/07_file_link.result.json').read_text())['result']
    ld=link['structuredContent']['data'];assert not ld['bytes_included'] and ld['delivery']=='link'
    uri=link['content'][1]['uri'];u=urlparse(uri)
    assert u.scheme=='https' and u.path=='/runner/result_source'
    assert set(parse_qs(u.query))=={'task_id','result_source_name'}
    assert ld['requires_auth'] is True and 'content_base64' not in ld;count+=1
    error=json.loads((ROOT/'examples/mcp/08_upload_too_large.result.json').read_text())['result']
    assert error['isError'] and not error['structuredContent']['data']['retry_old_url'];count+=1
    for p in (ROOT/'examples/mcp').glob('*.result.json'):
        r=json.loads(p.read_text())['result']
        if p.name not in {'05_upload.result.json','08_upload_too_large.result.json'}: assert json.loads(r['content'][0]['text'])==r['structuredContent']
        count+=1
    mutations=[('relative',{'file_path':'x.abc'}),('wrong-os',{'client_os':'plan9'}),('nul',{'file_path':'/tmp/x\x00.abc'}),('new-field',{'local_path':'/etc/passwd'})]
    for label,patch in mutations:
        a={**calls['runner_upload'],**patch}
        try:validate_upload(a,tools['runner_upload']['inputSchema'])
        except Exception:rejected+=1
        else:raise AssertionError('accepted invalid fixture '+label)
    for name,patch in [('runner_result',{'path':'/etc/passwd'}),('runner_result_source',{'mode':'execute'}),('runner_result_source',{'output_dir':'/root'}),('runner_submit',{'endpoint':'https://other.invalid'})]:
        a={**calls[name],**patch}
        assert not Draft202012Validator(tools[name]['inputSchema']).is_valid(a);rejected+=1
    diagrams=[]
    for p in sorted((ROOT/'diagrams').glob('*.mmd')):
        t=p.read_text();assert t.lstrip().startswith('sequenceDiagram');stack=[]
        names=set()
        for l in t.splitlines():
            l=l.strip()
            d=re.match(r'(?:participant|actor)\s+(\w+)',l)
            if d:names.add(d.group(1))
            first=l.split(' ',1)[0]
            if first in {'alt','loop','par','opt','critical','rect','break'}:stack.append(first)
            elif first=='end':assert stack,p.name;stack.pop()
        assert not stack,p.name
        for a,b in re.findall(r'^\s*(\w+)\s*[-.]+>{1,2}\s*(\w+)\s*:',t,re.M):assert a in names and b in names,(p.name,a,b)
        assert 'participant IM' not in t and '服务型Skill客户端' not in t
        diagrams.append(p.name)
    main=(ROOT/'10_Runner接口MCP封装与文件传输.md').read_text()
    assert all(n in main for n in expected)
    forbidden=('external_workflow_task','external_workflow_processor','/root/external-workflow-client-env','workflow_asset_id')
    for p in [*ROOT.glob('*.md'),*(ROOT/'examples').rglob('*'),*(ROOT/'diagrams').glob('*.mmd')]:
        if p.is_file():
            s=p.read_text()
            assert not any(x in s for x in forbidden),p
    return {'version':'1.6','scope':'static documentation contract validation only','passed':True,'positive_checks':count,'invalid_input_fixtures_rejected':rejected,'exact_tools':sorted(expected),'model_registrations_added_for_mcp':0,'mermaid_structure_checked':diagrams,'mermaid_parser_or_renderer_run':False,'live_http_mcp_tests_run':False,'business_code_modified':False,'model_tests_run':False}
if __name__=='__main__':
    try:print(json.dumps(check(),ensure_ascii=False,indent=2))
    except Exception as e:print(f'FAIL: {type(e).__name__}: {e}',file=sys.stderr);sys.exit(1)
