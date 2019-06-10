# oVirt Ansible SRIOV Module

In order to use this module, copy the ovirt_sriov.py file to /usr/share/ansible/plugins/modules with 0644 permissions.

## Documentation
```
module: ovirt_sriov
short_description: Module to manage SR-IOV VFs of host networks in oVirt/RHV
version_added: "2.7"
author: "Mike De Leon (@miked235)"
description:
    - "This module manages SR-IOV VFs in oVirt/RHEV."
    - "Your NIC must support SR-IOV and you must have oVirt/RHEV version 4.2+. Tested on 4.2/3"
options:
    name: 
        description:
            - "Name of the host the C(interface) resides on."
        required: true
    interface:
        description:
            - "Name of the interface to manage."
        required: true
    vfs:
        description:
            - "Number of desired VFs. This should only be set once, otherwise you will
               receive errors due to VFs being in use."
        type: int
    allowed_networks:
        description:
            - "Should be I(all) or I(specific)."
            - "I(all) allows any logical network on the host to create VFs from the C(interface)."
            - "I(specific) requires you to specify logical networks in the C(networks) option. By 
               choosing I(specific), only the provided C(networks) will be allowed to create VFs 
               from the C(interface)." 
        choices: ['all','specific']
    networks:
        description:
            - "List of logical networks allowed to created VFs on the C(interface). If C(allowed_networks)
               is set to I(specific), this setting is I(required)."
    labels:
        description:
            - "List of labels to add to the specific C(networks). You I(cannot) add labels when 
               C(allowed_networks) is set to I(all). C(labels) is ignored when C(allowed_networks)
               is set to I(all)."

extends_documentation_fragment: ovirt
```

## Examples
```
# Examples don't contain auth parameter for simplicity,
# look at ovirt_auth module to see how to reuse authentication:

# Create 4 VFs on interface eth1 on host 'host1' in the example cluster/data center. 
- name: Create VFs
  ovirt_sriov:
    name: example.host1
    interface: eth1
    vfs: 4
    
# Create 4 VFs with all networks allowed
- name: Create VFs with specific networks
  ovirt_sriov:
    name: example.host1
    interface: eth1
    vfs: 4
    allowed_networks: all
  
# Create 4 VFs on interface eth1 and only allow the net1 network to create VFs
- name: Create VFs with specific networks
  ovirt_sriov:
    name: example.host1
    interface: eth1
    vfs: 4
    allowed_networks: specific
    networks:
      - net1
    
# Everything in one
- name: Create VFs
  ovirt_sriov:
    name: example.host1
    interface: eth1
    vfs: 4
    allowed_networks: specific
    networks:
      - net1
      - net2
    labels:
      - passive
```

# Return Values
```
id:
    description: ID of the SR-IOV host NIC managed.
    returned: On success if host NIC is found.
    type: str
    sample: 7de90f31-222c-436c-a1ca-7e655bd5b60c
sriov_config:
    description: "Dictionary of all the host NIC VF attributes."
    returned: On success if host NIC is found.
    type: dict
network_ids:
    description: IDs of the networks allowed to create VFs from the interface. Will return None
                 when allowed_networks is set to all.
    returned: On success if host NIC is SR-IOV enabled.
    type: list
    sample: a0e60ec0-67a0-4209-a5d1-e7e563a061b5
labels:
    description: Label names given to the specific networks allowed to create VFs from the interface.
                 Will return None if no labels were given, or allowed_networks is set to all.
```
