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
TEST_VNFD_RED = "test-vnfd1.yaml"
TEST_VNFD_BLUE = "test-vnfd2.yaml"


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

    compute_clients = test_utils.get_ssh_clients(compute_nodes)

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

    tosca_red = os.path.join(DEMO_DIR,
                             VNFD_DIR,
                             TEST_VNFD_RED)
    os_tacker.create_vnfd(tacker_client, tosca_file=tosca_red)

    tosca_blue = os.path.join(DEMO_DIR,
                              VNFD_DIR,
                              TEST_VNFD_BLUE)
    os_tacker.create_vnfd(tacker_client, tosca_file=tosca_blue)

    default_param_file = os.path.join(
        DEMO_DIR,
        VNFD_DIR,
        VNFD_DEFAULT_PARAMS_FILE)

    test_utils.create_vnf_in_av_zone(
        tacker_client, vnfs[0], 'test-vnfd1',
        default_param_file, testTopology[vnfs[0]])
    test_utils.create_vnf_in_av_zone(
        tacker_client, vnfs[1], 'test-vnfd2',
        default_param_file, testTopology[vnfs[1]])

    vnf1_id = os_tacker.wait_for_vnf(tacker_client, vnf_name='testVNF1')
    vnf2_id = os_tacker.wait_for_vnf(tacker_client, vnf_name='testVNF2')
    if vnf1_id is None or vnf2_id is None:
        logger.error('ERROR while booting vnfs')
        sys.exit(1)

    instances = os_utils.get_instances(nova_client)
    for instance in instances:
        if ('client' not in instance.name) and ('server' not in instance.name):
            os_utils.add_secgroup_to_instance(nova_client, instance.id, sg_id)

    os_tacker.create_sfc(tacker_client, 'red', chain_vnf_names=['testVNF1'])
    os_tacker.create_sfc(tacker_client, 'blue', chain_vnf_names=['testVNF2'])

    os_tacker.create_sfc_classifier(
        tacker_client, 'red_http', sfc_name='red',
        match={
            'source_port': 0,
            'dest_port': 80,
            'protocol': 6
        })

    os_tacker.create_sfc_classifier(
        tacker_client, 'red_ssh', sfc_name='red',
        match={
            'source_port': 0,
            'dest_port': 22,
            'protocol': 6
        })

    logger.info(test_utils.run_cmd('tacker sfc-list')[1])
    logger.info(test_utils.run_cmd('tacker sfc-classifier-list')[1])

    num_chains = 2

    # Start measuring the time it takes to implement the classification rules
    t1 = threading.Thread(target=test_utils.wait_for_classification_rules,
                          args=(ovs_logger, compute_nodes, odl_ip, odl_port,
                                testTopology,))

    try:
        t1.start()
    except Exception, e:
        logger.error("Unable to start the thread that counts time %s" % e)

    server_ip, client_ip, sf1, sf2 = test_utils.get_floating_ips(
        nova_client, neutron_client)

    logger.info("Client VM IP: {0}".format(client_ip))
    logger.info("Server VM IP: {0}".format(server_ip))

    if not test_utils.check_ssh([sf1, sf2]):
        logger.error("Cannot establish SSH connection to the SFs")
        sys.exit(1)

    logger.info("Starting HTTP server on %s" % server_ip)
    if not test_utils.start_http_server(server_ip):
        logger.error(
            '\033[91mFailed to start HTTP server on %s\033[0m' % server_ip)
        sys.exit(1)

    logger.info("Starting HTTP firewall on %s" % sf2)
    test_utils.vxlan_firewall(sf2, port="80")
    logger.info("Starting SSH firewall on %s" % sf1)
    test_utils.vxlan_firewall(sf1, port="22")

    logger.info("Wait for ODL to update the classification rules in OVS")
    t1.join()

    logger.info("SSH traffic from client to server should be blocked")
    logger.info("HTTP traffic from client to server should be accepted")


if __name__ == '__main__':
    main()
