#!/usr/bin/python
# -*- coding: utf-8 -*-

ANSIBLE_METADATA = {'metadata_version': '1.0',
                    'status': ['preview'],
                    'supported_by': 'community'}

DOCUMENTATION = '''
---
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
'''

EXAMPLES = '''
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
    
'''

RETURN = '''
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
'''

import traceback

try:
    import ovirtsdk4.types as otypes
except ImportError:
    pass

from ansible.module_utils import six
from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.ovirt import (
    BaseModule,
    check_sdk,
    create_connection,
    equal,
    get_dict_of_struct,
    get_entity,
    get_link_name,
    ovirt_full_argument_spec,
    search_by_name,
)

class SRIOVModule(BaseModule):

    def build_entity(self):
        return otypes.HostNicVirtualFunctionsConfiguration()

    def get_network_ids(self, networks_service):
        networks = self._module.params['networks']
        network_ids = []
        if networks:
            for network in networks:
                network_ids.append(search_by_name(networks_service, network).id)  # TODO testing

        return network_ids

    def get_vf_config(self, nics_service):
        interface = self._module.params['interface']
        nic_with_attributes = [e for e in nics_service.list(headers={'All-content': True}) if e.name == interface]

        return nic_with_attributes[0].virtual_functions_configuration

    def get_vf_network_ids(self, nic_service):
        networks_list = nic_service.virtual_function_allowed_networks_service().list()
        network_ids = []
        if networks_list:
            for network in networks_list:
                network_ids.append(network.id)

        return network_ids

    def get_vf_labels(self, nic_service):
        vf_labels = nic_service.virtual_function_allowed_labels_service().list()
        labels = []
        if vf_labels:
           for label in vf_labels:
              labels.append(label.id)

        return labels

    def has_updates(self, networks_service, nics_service, nic_service):
        update = False
        allowed_networks = self._module.params['allowed_networks']
        vfs = self._module.params['vfs']
        vf_labels = self._module.params['labels']
        vf_config = self.get_vf_config(nics_service)

        # Check if allowed_networks needs updating
        if allowed_networks:
            all_networks = True if allowed_networks == 'all' else False

            if all_networks != vf_config.all_networks_allowed:
                update = True

            # Check if specific networks need updating
            if not all_networks:
                existing_networks = self.get_vf_network_ids(nic_service)
                desired_networks = self.get_network_ids(networks_service)
                if sorted(existing_networks) != sorted(desired_networks):
                    update = True

        # Check if labels need updating
        if vf_labels and allowed_networks == 'specific':
            vf_existing_labels = self.get_vf_labels(nic_service)
            if sorted(vf_labels) != sorted(vf_existing_labels):
                update = True

        # Check if the number of vfs needs updating
        if vfs:
            if vfs != vf_config.number_of_virtual_functions:
                update = True

        # Finally, return result
        return update

    def update_vf_labels(self, nic_service):
        vf_labels = self._module.params['labels']
        vf_labels_service = nic_service.virtual_function_allowed_labels_service()
        vf_existing_labels = self.get_vf_labels(nic_service)
        changed = False

        # Remove any unwanted labels
        remove_labels = list(set(vf_existing_labels).difference(vf_labels))
        if remove_labels:
            for label in remove_labels:
                vf_labels_service.service(label).remove()
            changed = True

        # Add any new labels
        add_labels = list(set(vf_labels).difference(vf_existing_labels))
        if add_labels:
            for label in add_labels:
                vf_labels_service.add(otypes.NetworkLabel(
                    id=label,
                    host_nic=nic_service.get()
                )
                )
            changed = True

        if changed:
            self.changed = True

    def update_vf_allowed_networks(self, nics_service, nic_service):
        all_networks = True if self._module.params['allowed_networks'] == 'all' else False
        vf_config = self.get_vf_config(nics_service)
        changed = False

        if all_networks != vf_config.all_networks_allowed:
            vf_config = otypes.HostNicVirtualFunctionsConfiguration(
                all_networks_allowed=all_networks
            )
            nic_service.update_virtual_functions_configuration(virtual_functions_configuration=vf_config)
            changed = True

        if changed:
            self.changed = True

    def update_vf_networks(self, networks_service, nic_service):
        vf_allowed_networks_service = nic_service.virtual_function_allowed_networks_service()
        vf_existing_networks = self.get_vf_network_ids(nic_service)
        vf_desired_networks = self.get_network_ids(networks_service)
        changed = False

        # Remove any unwanted networks
        remove_networks = list(set(vf_existing_networks).difference(vf_desired_networks))
        if remove_networks:
            for network in remove_networks:
                vf_allowed_networks_service.network_service(network).remove()
            changed = True

        # Add any new networks
        add_networks = list(set(vf_desired_networks).difference(vf_existing_networks))
        if add_networks:
            for network in add_networks:
                vf_allowed_networks_service.add(networks_service.network_service(network).get())
            changed = True

        if changed:
            self.changed = True

    def update_number_of_vfs(self, nics_service, nic_service):
        vf_config = self.get_vf_config(nics_service)
        vfs = self._module.params['vfs']
        changed = False

        if vfs != vf_config.number_of_virtual_functions:
            vf_config = otypes.HostNicVirtualFunctionsConfiguration(
                number_of_virtual_functions=vfs,
            )
            nic_service.update_virtual_functions_configuration(virtual_functions_configuration=vf_config)
            changed = True

        if changed:
            self.changed = True


def main():
    # Module Args
    argument_spec = ovirt_full_argument_spec(
        name=dict(aliases=['host'], required=True),
        interface=dict(required=True),
        vfs=dict(default=None, type='int'),
        allowed_networks=dict(
            choices=['all', 'specific'],
            default=None,
        ),
        networks=dict(default=None, type='list'),
        labels=dict(default=None, type='list'),
    )

    # Create & check module
    module = AnsibleModule(
        argument_spec=argument_spec, 
        supports_check_mode=True,
    )
    
    check_sdk(module)
    
    try:
        # Connection to oVirt
        auth = module.params.pop('auth')
        connection = create_connection(auth)
        hosts_service = connection.system_service().hosts_service()
        sriov_module = SRIOVModule(
                connection=connection,
                module=module,
                service=hosts_service,
        )

        # Verify host exists
        host = sriov_module.search_entity()
        if host is None:
            raise Exception("Host '%s' was not found." % module.params['name'])

        # Params
        interface = module.params['interface']
        vfs = module.params['vfs']
        allowed_networks = module.params['allowed_networks']
        networks = module.params['networks']
        labels = module.params['labels']
        
        # Host services
        hosts_service = connection.system_service().hosts_service()
        networks_service = connection.system_service().networks_service()
        host_service = hosts_service.host_service(host.id)
        nics_service = host_service.nics_service()

        # Verify interface exists
        nic = search_by_name(nics_service, interface)
        if nic is None:
            raise Exception("Interface '%s' was not found." % module.params['interface'])
        else:
            nic_service = nics_service.nic_service(nic.id)

        # Verify given networks exist
        if networks:
            for network in networks:
                if search_by_name(networks_service, network) is None:
                    raise Exception("Network '%s' was not found." % network)

        # Check for and apply updates
        if sriov_module.has_updates(networks_service, nics_service, nic_service):
            if allowed_networks:
                sriov_module.update_vf_allowed_networks(nics_service, nic_service)
                if allowed_networks == 'specific':
                    sriov_module.update_vf_networks(networks_service, nic_service)
                    if labels:
                        sriov_module.update_vf_labels(nic_service)
            if vfs:
                sriov_module.update_number_of_vfs(nics_service, nic_service)

        vf_config = sriov_module.get_vf_config(nics_service)

        module.exit_json(**{
            'changed': sriov_module.changed,
            'id': nic.id if nic else None,
            'sriov_config': get_dict_of_struct(vf_config),
            'network_ids': sriov_module.get_vf_network_ids(nic_service),
            'labels': sriov_module.get_vf_labels(nic_service),
        })

    # Catch exceptions and logout
    except Exception as e:
        module.fail_json(msg=str(e), exception=traceback.format_exc())
    finally:
        connection.close(logout=auth.get('token') is None)
        
if __name__ == "__main__":
    main()