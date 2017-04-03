import os
import sys

import functest.utils.functest_logger as ft_logger
import functest.utils.functest_utils as ft_utils
import functest.utils.openstack_utils as os_utils

import sfc.lib.utils as test_utils
from opnfv.deployment.factory import Factory as DeploymentFactory
import sfc.lib.topology_shuffler as topo_shuffler


logger = ft_logger.Logger(__name__).getLogger()

CLIENT = "client"
SERVER = "server"
FLAVOR = "custom"
RAM_SIZE_IN_MB = "1500"
DISK_SIZE_IN_GB = "10"
VCPU_COUNT = "1"
IMAGE_NAME = "sfc_nsh_danube"
IMAGE_FILE_NAME = "sfc_nsh_danube.qcow2"
IMAGE_FORMAT = "qcow2"
IMAGE_URL = "http://artifacts.opnfv.org/sfc/images"
DIR_FUNCTEST_DATA = ft_utils.get_functest_config(
    "general.dir.functest_data")
IMAGE_PATH = os.path.join(
   DIR_FUNCTEST_DATA, IMAGE_FILE_NAME)
NET_NAME = "example-net"
SUBNET_NAME = "example-subnet"
ROUTER_NAME = "example-router"
SUBNET_CIDR = "11.0.0.0/24"
SECGROUP_NAME = "example-sg"
SECGROUP_DESCR = "Example Security group"
INSTALLER = {
    "type": "fuel",
    "ip": "10.20.0.2",
    "user": "root",
    "password": "r00tme",
    "cluster": "1"
}


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

    controller_nodes = [node for node in openstack_nodes
                        if node.is_controller()]
    compute_nodes = [node for node in openstack_nodes
                     if node.is_compute()]

    odl_ip, odl_port = test_utils.get_odl_ip_port(openstack_nodes)

    for compute in compute_nodes:
        logger.info("This is a compute: %s" % compute.info)

    test_utils.setup_compute_node(SUBNET_CIDR, compute_nodes)
    test_utils.configure_iptables(controller_nodes)

    test_utils.download_image(IMAGE_URL, IMAGE_PATH)
    _, custom_flv_id = os_utils.get_or_create_flavor(
        FLAVOR,
        RAM_SIZE_IN_MB,
        DISK_SIZE_IN_GB,
        VCPU_COUNT, public=True)
    if not custom_flv_id:
        logger.error("Failed to create custom flavor")
        sys.exit(1)

    glance_client = os_utils.get_glance_client()
    neutron_client = os_utils.get_neutron_client()
    nova_client = os_utils.get_nova_client()

    image_id = os_utils.create_glance_image(glance_client,
                                            IMAGE_NAME,
                                            IMAGE_PATH,
                                            IMAGE_FORMAT,
                                            public='public')

    network_id = test_utils.setup_neutron(neutron_client,
                                          NET_NAME,
                                          SUBNET_NAME,
                                          ROUTER_NAME,
                                          SUBNET_CIDR)

    sg_id = test_utils.create_security_groups(neutron_client,
                                              SECGROUP_NAME,
                                              SECGROUP_DESCR)

    vnfs = ['testVNF1', 'testVNF2']

    topo_seed = 0
    testTopology = topo_shuffler.topology(vnfs, seed=topo_seed)

    logger.info('This test is run with the topology {0}'
                .format(testTopology['id']))
    logger.info('Topology description: {0}'
                .format(testTopology['description']))

    test_utils.create_instance(
        nova_client, CLIENT, FLAVOR, image_id,
        network_id, sg_id, av_zone=testTopology['client'])

    srv_instance = test_utils.create_instance(
        nova_client, SERVER, FLAVOR, image_id,
        network_id, sg_id, av_zone=testTopology['server'])

    srv_prv_ip = srv_instance.networks.get(NET_NAME)[0]
    logger.info('SERVER PRIVATE IP: {0}'.format(srv_prv_ip))


if __name__ == '__main__':
    main()
