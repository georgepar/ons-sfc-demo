import os

import functest.utils.functest_logger as ft_logger
import functest.utils.openstack_utils as os_utils
import sfc.lib.utils as sfc_utils

from opnfv.deployment.factory import Factory as DeploymentFactory


logger = ft_logger.Logger("Fetch Credentials").getLogger()

INSTALLER = {
    "type": "fuel",
    "ip": "10.20.0.2",
    "user": "root",
    "password": "r00tme",
    "cluster": "1"
}

RC_FILE = "/home/opnfv/demo/basic/tackerc"


def fetch_tackerc_file(controller_node):
    if os.path.exists(RC_FILE):
        os.remove(RC_FILE)

    controller_node.get_file("/root/tackerc", RC_FILE)
    return RC_FILE


def main(report=False):
    deploymentHandler = DeploymentFactory.get_handler(
        INSTALLER["type"],
        INSTALLER["ip"],
        INSTALLER["user"],
        installer_pwd=INSTALLER["password"])

    cluster = INSTALLER["cluster"]
    nodes = (deploymentHandler.get_nodes({'cluster': cluster})
             if cluster is not None
             else deploymentHandler.get_nodes())

    a_controller = [node for node in nodes
                    if node.is_controller()][0]

    rc_file = fetch_tackerc_file(a_controller)
    os_utils.source_credentials(rc_file)

    odl_ip, odl_port = sfc_utils.get_odl_ip_port(nodes)

    with open("odlrc", "w") as f:
        f.write("#!/usr/bin/env bash\n")
        f.write("export ODL_IP={0}\n".format(odl_ip))
        f.write("export ODL_PORT={0}\n".format(odl_port))

    logger.info("Tacker creds fetched in {0}".format(RC_FILE))
    logger.info("OpenDaylight IP: {0}".format(odl_ip))
    logger.info("OpenDaylight port: {0}".format(odl_port))


if __name__ == '__main__':
    main()
