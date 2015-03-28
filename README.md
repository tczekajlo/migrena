# migrena
Migrena is a simple script to copy disk (instance) between two Openstack environments. 

# How does it work?
1. Migrena create new instance in the target environment via Nova API. It's very important to boot destination instance using the same image like in the source instance, also the size of disk in flavor have to be the same.
2. After created the destination instance, the script stops both instances (source and destination).
3. Migrena run nbd-server to export disk on hypervisor where is located source instance.
4. Mirgena run nbd-client on hypervisor where is located destinantion instance.
5. The script reads backing file of disk from destination instance.
6. In this step, disk is copy to destination.
7. The script do rebase on the copied disk.

Actually that's all. Additionally you can use -a argument to say that you want to start VMs at the end. 

#Requirements
Migrena require the following modules and tools.

Python modules:
- paramiko
- argparse
- novaclient
- glanceclient
- keystoneclient

Tools:
- on each hypervisor should be installed nbd-server, nbd-client and qemu-img tool.

Additionally between hypervisors and host where is run migrena has to be access via ssh.

#Arguments
|Short name|Full name|Default value|Description|
|----------|---------|-------------|-----------|
|-s|--src-uid|None|UUID of source instance.|
|-d|--dst-name|None|Name of destination instance.|
|-f|--flavor|None|Name of flavor used to create instance.|
|-i|--image-id|None|Name of image used to create instance.|
|-e|--extra-args|None|Extra parameters used to create instance.|
|-a|--start-after|all|After all operations start instance. Default starts both instances. You can choose which instance run, ex. -a src|

#Configuration
```python
#Path to disk file. The path has to be the same in the both environment.
DISK_PATH="/opt/stack/data/nova/instances/%s/disk"

#Name of NBD device
NBD_DEVICE="/dev/nbd15"

#Port number for nbd-server
NBD_SERVER_PORT=2666

#Credentials to source environment. 
SRC_CREDS = {
        'auth_url': 'http://10.0.2.15:5000/v2.0',
        'username': 'admin',
        'password': 'pass',
        'tenant_name': 'demo'
        }

#Credentials to target environment.
DST_CREDS = {
        'auth_url': 'http://10.0.3.15:5000/v2.0',
        'username': 'admin',
        'password': 'pass',
        'tenant_name': 'admin'
        }

#Glance ednpoint url.
DST_GLANCE_ENDPOINT='http://10.0.2.5:9292'
```
# Example of use
```
./migrena.py -s c84cf4ce-922c-44dc-86d2-c16a777be305 -d destination_vm -f m1.nano -i aa50a64f-065a-4c6b-a033-bae0b7f7ef6a -e "{'nics':[{'net-id': '990571f4-fbc5-484f-8eec-92f56c84e5fa'}], 'security_groups': ['default']}" -a
Create new instance in the target environment.
Name: destination_vm
Flavor: m1.nano, ID: 42
Image: cirros-0.3.2-x86_64-uec, ID: aa50a64f-065a-4c6b-a033-bae0b7f7ef6a
Extra args:
 nics: [{'net-id': '990571f4-fbc5-484f-8eec-92f56c84e5fa'}]
 security_groups: ['default']
Done. Current status: ACTIVE

Stop source instance.
Done. Current status: SHUTOFF

Stop destination instance.
Done. Current status: SHUTOFF

Migrate disk to destination instance
* Running NBD server on source node.
* Running NBD client on destination node.
* Checking backing file on destination disk.
** Backing file: /opt/stack/data/nova/instances/_base/bff3829ef435b8994c2a5f5ac5d154441abc5578
* Copying disk.
 [##################################################] 2 / 2 MB
* Rebase backing file on disk
Start c84cf4ce-922c-44dc-86d2-c16a777be305 instance.
Done. Current status: ACTIVE

Start 9e5c8644-bc25-4207-85cc-66c51f81c956 instance.
Done. Current status: ACTIVE
```
