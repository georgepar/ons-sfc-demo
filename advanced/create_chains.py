#!/bin/python
#
# Copyright (c) 2015 All rights reserved
# This program and the accompanying materials
# are made available under the terms of the Apache License, Version 2.0
# which accompanies this distribution, and is available at
#
# http://www.apache.org/licenses/LICENSE-2.0
#

import os
import re
import sys
import threading

import functest.utils.functest_logger as ft_logger
import functest.utils.openstack_tacker as os_tacker
import functest.utils.openstack_utils as os_utils
import opnfv.utils.ovs_logger as ovs_log

import sfc.lib.utils as test_utils
from opnfv.deployment.factory import Factory as DeploymentFactory
import sfc.lib.topology_shuffler as topo_shuffler


logger = ft_logger.Logger(__name__).getLogger()


SECGROUP_NAME = "example-sg"
INSTALLER = {
    "type": "fuel",
    "ip": "10.20.0.2",
    "user": "root",
    "password": "r00tme",
    "cluster": "1"
}
DEMO_DIR = "/home/opnfv/demo/basic/"
RESULTS_DIR = "/home/opnfv/functest/results/"
VNFD_DIR = "vnfd-templates"
VNFD_DEFAULT_PARAMS_FILE = "test-vnfd-default-params.yaml"
TEST_VNFD = "test-vnfd1.yaml"


def main():
    deploymentHandler = DeploymentFactory.get_handler(
        INSTALLER["type"],
        INSTALLER["ip"],
        INSTALLER["user"],
        installer_pwd=INSTALLER["password"])

    cluster = INSTALLER["cluster"]
    openstack_nodes = (deploymentHandler.get_nodes({'cluster': cluster})
                       if cluster is not None
                       else deploymentHandler.get_nodes())

    compute_nodes = [node for node in openstack_nodes
                     if node.is_compute()]

    odl_ip, odl_port = test_utils.get_odl_ip_port(openstack_nodes)

    neutron_client = os_utils.get_neutron_client()
    nova_client = os_utils.get_nova_client()
    tacker_client = os_tacker.get_tacker_client()

    ovs_logger = ovs_log.OVSLogger(
        os.path.join(DEMO_DIR, 'ovs-logs'), RESULTS_DIR)

    sg_id = os_utils.get_security_group_id(neutron_client, SECGROUP_NAME)

    vnfs = ['testVNF1', 'testVNF2']

    topo_seed = 0
    testTopology = topo_shuffler.topology(vnfs, seed=topo_seed)

    logger.info('This test is run with the topology {0}'
                .format(testTopology['id']))
    logger.info('Topology description: {0}'
                .format(testTopology['description']))

    tosca_red = os.path.join(DEMO_DIR, VNFD_DIR, TEST_VNFD)
    os_tacker.create_vnfd(tacker_client, tosca_file=tosca_red)

    default_param_file = os.path.join(
        DEMO_DIR, VNFD_DIR, VNFD_DEFAULT_PARAMS_FILE)

    test_utils.create_vnf_in_av_zone(
        tacker_client, vnfs[0], 'test-vnfd1',
        default_param_file, testTopology[vnfs[0]])

    vnf_id = os_tacker.wait_for_vnf(tacker_client, vnf_name='testVNF1')
    if vnf_id is None:
        logger.error('ERROR while booting vnf')
        sys.exit(1)

    vnf_instance_id = test_utils.get_nova_id(tacker_client, 'vdu1', vnf_id)

    instances = os_utils.get_instances(nova_client)
    for instance in instances:
        if ('client' not in instance.name) and ('server' not in instance.name):
            os_utils.add_secgroup_to_instance(nova_client, instance.id, sg_id)

    os_tacker.create_sfc(tacker_client, 'red', chain_vnf_names=['testVNF1'])

    os_tacker.create_sfc_classifier(
        tacker_client, 'red_http', sfc_name='red',
        match={
            'source_port': 0,
            'dest_port': 80,
            'protocol': 6
        })

    os_tacker.create_sfc_classifier(
        tacker_client, 'red_http_reverse', sfc_name='red',
        match={
            'source_port': 80,
            'dest_port': 0,
            'protocol': 6
        })

    logger.info(test_utils.run_cmd('tacker sfc-list')[1])
    logger.info(test_utils.run_cmd('tacker sfc-classifier-list')[1])

    # Start measuring the time it takes to implement the classification rules
    t1 = threading.Thread(target=test_utils.wait_for_classification_rules,
                          args=(ovs_logger, compute_nodes, odl_ip, odl_port,
                                testTopology,))

    try:
        t1.start()
    except Exception, e:
        logger.error("Unable to start the thread that counts time %s" % e)

    sf_floating_ip = test_utils.assign_floating_ip(
        nova_client, neutron_client, vnf_instance_id)

    for ip in (sf_floating_ip):
        logger.info("Checking connectivity towards floating IP [%s]" % ip)
        if not test_utils.ping(ip, retries=50, retry_timeout=1):
            logger.error("Cannot ping floating IP [%s]" % ip)
            sys.exit(1)
        logger.info("Successful ping to floating IP [%s]" % ip)

    if not test_utils.check_ssh([sf_floating_ip]):
        logger.error("Cannot establish SSH connection to the SFs")
        sys.exit(1)

    logger.info("Firewall started, blocking traffic port 80")
    test_utils.vxlan_firewall(sf_floating_ip, port=80)

    logger.info("Wait for ODL to update the classification rules in OVS")
    t1.join()

    for compute_node in compute_nodes:
        compute_ssh = compute_node.ssh_client
        match_rsp = re.compile(
            r'.+tp_dst=([0-9]+).+load:(0x[0-9a-f]+)->NXM_NX_NSP\[0\.\.23\].+')
        # First line is OFPST_FLOW reply (OF1.3) (xid=0x2):
        # This is not a flow so ignore
        flows = (ovs_logger.ofctl_dump_flows(compute_ssh, 'br-int', '11')
                 .strip().split('\n')[1:])
        matching_flows = [match_rsp.match(f) for f in flows]
        logger.info(matching_flows)

    logger.info("HTTP traffic from client to server should be accepted")


if __name__ == '__main__':
    main()