'''Offline checks for the JSON -> fac.yaml transform and validation (no API calls).'''

import copy

import yaml

from convert import check_spec, dump_yaml, escape_description, to_fac_config

SPEC = {
    'skill_name': 'demo',
    'operations': [{'id': 'op1', 'excerpt': 'plan tickets', 'category': 'operation', 'note': 'plan.json'}],
    'artifacts': [{'path': 'plan.json', 'purpose': 'ticket list', 'from_operations': ['op1']}],
    'final_target': 'tickets.md',
    'targets': [
        {'path': 'plan.json', 'description': 'List tickets for `input.md`.\nCost: $5', 'cmd': None,
         'schema': '{"type": "object"}', 'dependencies': [{'target': 'input.md', 'include': True}], 'variables': []},
        {'path': 'tickets/$ID.md', 'description': 'Write ticket $ID.', 'cmd': None, 'schema': None,
         'dependencies': [{'target': 'plan.json', 'include': False}, {'target': 'input.md', 'include': True}],
         'variables': [{'name': 'ID', 'command': "jq -r '.tickets[].id' plan.json"}]},
        {'path': 'tickets.md', 'description': None, 'cmd': 'cat tickets/*.md > tickets.md', 'schema': None,
         'dependencies': [{'target': 'tickets/$ID.md', 'include': True}], 'variables': []},
    ],
}


def test_valid_spec_converts_to_fac_yaml():
    assert check_spec(SPEC) == []
    config = yaml.safe_load(dump_yaml(to_fac_config(SPEC, 'some/model')))
    assert config['plan.json']['model'] == 'openrouter/some/model'
    assert config['plan.json']['dependencies'] == [{'target': 'input.md', 'in_fac.yaml': False}]
    assert config['tickets/$ID.md']['variables'] == {'ID': "jq -r '.tickets[].id' plan.json"}
    assert config['tickets/$ID.md']['description'] == 'Write ticket $ID.'
    assert 'model' not in config['tickets.md']


def test_escape_description_keeps_only_declared_variables():
    assert escape_description('run `x` for $ID, $HOME, ${ID}, $5, a\\b', {'ID'}) == \
        'run \\`x\\` for $ID, \\$HOME, ${ID}, \\$5, a\\\\b'


def test_check_spec_reports_broken_graphs():
    spec = copy.deepcopy(SPEC)
    spec['targets'][0]['dependencies'].append({'target': 'tickets.md', 'include': True})  # cycle
    spec['targets'][2]['dependencies'].append({'target': 'missing.md', 'include': True})
    errors = check_spec(spec)
    assert any('cycle' in e for e in errors)
    assert any('missing.md' in e for e in errors)
