from __future__ import annotations

from models import Dimension

CUSTOM_ITEM = '_custom'
OTHER_ITEM = '_other'

ALLOWLISTS: dict[Dimension, frozenset[str]] = {
    'provider': frozenset({
        'clab', 'external', 'libvirt', 'none', 'podman', 'virtualbox', 'vmware'
    }),
    'device': frozenset({
        'arubacx', 'bird', 'cat8000v', 'ceos', 'csr', 'cumulus', 'cumulus_nvue',
        'dellos10', 'eos', 'exos', 'fortios', 'frr', 'iol', 'ioll2', 'ios', 'iosv',
        'iosvl2', 'junos', 'linux', 'nxos', 'openbsd', 'routeros', 'routeros7',
        'sonic', 'srlinux', 'sros', 'vios', 'vjunos-router', 'vjunos-switch', 'vmx',
        'vpp', 'vptx', 'vsrx', 'vyos'
    }),
    'module': frozenset({
        'bfd', 'bgp', 'dhcp', 'eigrp', 'evpn', 'gateway', 'isis', 'lag', 'ldp',
        'lldp', 'mpls', 'ospf', 'rip', 'routing', 'sr', 'srv6', 'stp', 'vlan',
        'vrf', 'vrrp', 'vxlan'
    }),
    'plugin': frozenset({
        'bgp.session', 'files', 'multilab', 'nodeset', 'ospf.areas', 'validate',
        'vrf'
    }),
    'command': frozenset({
        'capture', 'clab', 'collect', 'config', 'connect', 'create', 'defaults',
        'down', 'exec', 'graph', 'help', 'initial', 'install', 'inspect', 'libvirt',
        'report', 'restart', 'show', 'status', 'tc', 'test', 'tools', 'up',
        'validate', 'version'
    })
}

_FIXED_DIMENSIONS: frozenset[Dimension] = frozenset({'topology', 'node', 'link'})


def normalize_item(dimension: Dimension, item: str) -> str:
    if dimension in _FIXED_DIMENSIONS:
        return 'all'

    if item in ALLOWLISTS.get(dimension, frozenset()):
        return item

    return OTHER_ITEM if dimension == 'command' else CUSTOM_ITEM
