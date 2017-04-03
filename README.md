# ons-sfc-demo
OPNFV SFC demo for ONS

## Basic Demo Instructions

1. Pull & run latest functest container:
   ```
   docker pull opnfv/functest:latest
   docker run --name=sfc-demo --privileged=true -dit -e INSTALLER_TYPE=fuel -e INSTALLER_IP=10.20.0.2 -e DEPLOY_SCENARIO=os-odl_l2-sfc-noha -e CI_DEBUG=false opnfv/functest:latest /bin/bash
   docker exec -ti sfc-demo bash
   ```
2. Clone this repo inside the container home directory (naming is important because it contains hardcoded paths):
   ```
   cd /home/opnfv/
   git clone https://github.com/georgepar/ons-sfc-demo/ demo
   ```
3. Bootstrap the environment:
   ```
   cd /home/opnfv/demo/basic
   bash bootstrap.sh
   ```
   This command 
   1. fetches the tacker credentials in `/home/opnfv/demo/basic/tackerc` and the ODL credentials in `/home/opnfv/demo/basic/odlrc`
   2. Creates `client` and `server` endpoints
   3. Creates 2 chains, `blue` and `red` and two classifiers `red_http` and `red_ssh` that pass http and ssh traffic through the `red` chain
   You can also run these steps independently using the `fetch_creds.py`, `create_endpoints.py` and `create_chains.py` scripts.
4. Run the demo. You can use `change_classification.sh` script to modify the classification rules so that the traffic goes through the `blue` chain
5. When done, clean everything up with
   ```
   source odlrc
   python cleanup.py $ODL_IP $ODL_PORT
   ```
