#!/usr/bin/python

from keystoneclient.auth.identity import v2 as identity
from keystoneclient import session
from glanceclient import Client
from novaclient import client

from ast import literal_eval
from random import randint

import paramiko
import argparse
import sys
import thread
import time

DISK_PATH="/opt/stack/data/nova/instances/%s/disk"
NBD_DEVICE="/dev/nbd15"
NBD_SERVER_PORT=2666

SRC_CREDS = {
        'auth_url': 'http://10.0.2.15:5000/v2.0',
        'username': 'admin',
        'password': 'pass',
        'tenant_name': 'demo'
        }

DST_CREDS = {
        'auth_url': 'http://10.0.3.15:5000/v2.0',
        'username': 'admin',
        'password': 'pass',
        'tenant_name': 'admin'
        }

DST_GLANCE_ENDPOINT='http://10.0.2.5:9292'

args=None
p_status = ['|', '/', '-']
__version__ = "0.0.1"

class migrena():
    def __init__(self):
        s_auth = identity.Password(**SRC_CREDS)
        s_session = session.Session(auth=s_auth)
        s_token = s_auth.get_token(s_session)

        d_auth = identity.Password(**DST_CREDS)
        d_session = session.Session(auth=d_auth)
        d_token = d_auth.get_token(d_session)

        #Nova
        self.s_nova = client.Client(2, session=s_session)
        self.d_nova = client.Client(2, session=d_session)

        #Glance
        self.d_glance = Client('2', endpoint=DST_GLANCE_ENDPOINT, token=d_token)

    def __bold(self, msg):
        return u'\033[1m%s\033[0m' % msg

    def __progress(self, current, total):
        prefix = '%d / %d MB' % (int(current/1000000), int(total/1000000))
        bar_start = ' ['
        bar_end = '] '

        bar_size = 50
        amount = int(current / (total / float(bar_size)))
        remain = bar_size - amount

        bar = '#' * amount + ' ' * remain
        return bar_start + bar + bar_end + self.__bold(prefix)


    def __get_dst_image(self, param, search):
        for image in self.d_glance.images.list():
            if image[param] == search:
                return image

    def __ssh_conn(self, host):
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        ssh.connect(host)

        return ssh


    def create_instance(self):
        flavor=self.d_nova.flavors.find(name=args.flavor).id
        image=args.image_id
        vm_name=args.dst_name
        extra_args = args.extra_args

        print self.__bold("Create new instance in the target environment.")
        print "Name: %s" % vm_name
        print "Flavor: %s, ID: %s" % (args.flavor, flavor)
        print "Image: %s, ID: %s" % (self.__get_dst_image("id", image)['name'], image)
        print "Extra args:"

        for k,v in literal_eval(extra_args).items():
            print " %s: %s" % (k,v)

        self.d_nova.servers.create(vm_name, image, flavor, **literal_eval(extra_args))

        vm = self.d_nova.servers.find(name=vm_name)

        while (getattr(self.d_nova.servers.get(vm.id),"OS-EXT-STS:power_state") != 1 and
                self.d_nova.servers.get(vm.id).status != "ACTIVE"):
            vm_status = self.d_nova.servers.get(vm.id).status
            if vm_status == "ERROR":
                print "Instance ERROR. Exit."
                sys.exit(1)
                
            sys.stdout.write('Current status: %s %s\r' % (vm_status, p_status[randint(0,2)]))
            sys.stdout.flush()
            time.sleep(1)

        print "Done. Current status: %s" % self.d_nova.servers.get(vm.id).status
        print ""

    def nbd_server(self, host, disk):
        ssh = self.__ssh_conn(host)
        stdin, stdout, stderr = ssh.exec_command("killall nbd-server; nbd-server %d -r %s" % (NBD_SERVER_PORT, disk))

        stderr.readlines()
        stdin.close()

    def nbd_client(self, server, client):
        ssh = self.__ssh_conn(client)
        stdin, stdout, stderr = ssh.exec_command("nbd-client -d %s; nbd-client %s %d %s" %
                (NBD_DEVICE, server, NBD_SERVER_PORT, NBD_DEVICE))
        stderr.readlines()
        stdout.readlines()
        stdin.close()

    def __stop_dst_instance(self, vm):

        print self.__bold("Stop destination instance.")

        if self.d_nova.servers.get(vm.id).status != "SHUTOFF":
            self.d_nova.servers.stop(vm.id)

        while self.d_nova.servers.get(vm.id).status != "SHUTOFF":
            vm_status = self.d_nova.servers.get(vm.id).status

            sys.stdout.write('Current status: %s %s\r' % (vm_status, p_status[randint(0,2)]))
            sys.stdout.flush()
            time.sleep(1)

        print "Done. Current status: %s" % self.d_nova.servers.get(vm.id).status
        print ""

    def __stop_src_instance(self, uuid):

        print self.__bold("Stop source instance.")

        if self.s_nova.servers.get(uuid).status != "SHUTOFF":
            self.s_nova.servers.stop(uuid)

        while self.s_nova.servers.get(uuid).status != "SHUTOFF":
            vm_status = self.s_nova.servers.get(uuid).status

            sys.stdout.write('Current status: %s %s\r' % (vm_status, p_status[randint(0,2)]))
            sys.stdout.flush()
            time.sleep(1)

        print "Done. Current status: %s" % self.s_nova.servers.get(uuid).status
        print ""

    def __start_instance(self, uuid, target):
        if target == 'dst':
            nova = self.d_nova
        elif target == 'src':
            nova = self.s_nova

        print self.__bold("Start %s instance." % uuid)

        if nova.servers.get(uuid).status != "ACTIVE":
            nova.servers.start(uuid)

        while nova.servers.get(uuid).status != "ACTIVE":
            vm_status = nova.servers.get(uuid).status

            sys.stdout.write('Current status: %s %s\r' % (vm_status, p_status[randint(0,2)]))
            sys.stdout.flush()
            time.sleep(1)

        print "Done. Current status: %s" % nova.servers.get(uuid).status
        print ""


    def __check_backing_file(self, hv, disk):
        ssh = self.__ssh_conn(hv)
        stdin, stdout, stderr = ssh.exec_command("qemu-img info %s" % disk)
        error = stderr.readlines()

        if len(error):
            print "Error: %s" % error
            sys.exit(1)

        return stdout.readlines()[5].strip().split(' ')[2]
    
    def __rebase_disk(self, host, base, disk):
        ssh = self.__ssh_conn(host)
        stdin, stdout, stderr = ssh.exec_command("qemu-img rebase -b %s %s" % (base, disk))
        error = stderr.readlines()

        if len(error):
            print "Error: %s" % error
            sys.exit(1)

    def __copy_disk(self, host, disk):
        ssh = self.__ssh_conn(host)
        stdin, stdout, stderr = ssh.exec_command("cat %s > %s" % (NBD_DEVICE, disk))
        error = stderr.readlines()

        if len(error):
            print "Error: %s" % error

    def __size_disk(self, host, disk):
        ssh = self.__ssh_conn(host)
        stdin, stdout, stderr = ssh.exec_command("stat -c '%%s' %s" % disk)
        error = stderr.readlines()

        if len(error):
            print "Error: %s" % error
            sys.exit(1)
        else:
            return int(stdout.readlines()[0])

    def migrate_disk(self):
        vm_name=args.dst_name
        vm = self.d_nova.servers.find(name=vm_name)

        src_hv = getattr(self.s_nova.servers.get(args.src_uuid), 'OS-EXT-SRV-ATTR:hypervisor_hostname')
        dst_hv = getattr(self.d_nova.servers.get(vm.id), 'OS-EXT-SRV-ATTR:hypervisor_hostname')
        
        self.__stop_src_instance(args.src_uuid)
        self.__stop_dst_instance(vm)

        print self.__bold("Migrate disk to destination instance")
        print "* Running NBD server on source node."

        src_disk = DISK_PATH % args.src_uuid
        dst_disk = DISK_PATH % vm.id

        self.nbd_server(src_hv, src_disk)

        print "* Running NBD client on destination node."
        self.nbd_client(src_hv, dst_hv)

        print "* Checking backing file on destination disk."
        backing_file=self.__check_backing_file(dst_hv,dst_disk)
        
        print "** Backing file: %s" % backing_file

        print "* Copying disk."
        src_disk_size = self.__size_disk(src_hv,src_disk)

        thread.start_new_thread(self.__copy_disk, (dst_hv, dst_disk,))

        dst_disk_size=0
        while src_disk_size != dst_disk_size:
            dst_disk_size = self.__size_disk(dst_hv,dst_disk)
            
            sys.stdout.write(self.__progress(dst_disk_size, src_disk_size) + '\r')
            sys.stdout.flush()
            time.sleep(5)
        print ""

        print "* Rebase backing file on disk"
        self.__rebase_disk(dst_hv, backing_file, dst_disk)

        if args.start_after != None:
            for target in args.start_after.split(','):
                if target == 'all':
                    self.__start_instance(args.src_uuid, 'src')
                    self.__start_instance(vm.id, 'dst')
                elif target == 'src':
                    self.__start_instance(args.src_uuid, 'src')
                elif target == 'dst':
                    self.__start_instance(vm.id, 'dst')

def parse_args():
    global args 

    parser = argparse.ArgumentParser(description="migrena " + __version__ + "", version="%(prog)s " + __version__)
    parser.add_argument('-s', '--src-uuid', help='UUID of source instance.', required=True)
    parser.add_argument('-d', '--dst-name', help='Name of destination instance.', required=True)
    parser.add_argument('-f', '--flavor', help='Name of flavor used to create instance.', required=True)
    parser.add_argument('-i', '--image-id', help='Name of image used to create instance.', required=True)
    parser.add_argument('-e', '--extra-args', help='Extra parameters used to create instance', required=True)
    parser.add_argument('-a', '--start-after', help='After all operations start instance. Default starts both instances.', const='all', nargs='?')

    args = parser.parse_args()
    
if __name__ == "__main__":
    parse_args()
    m = migrena()
    m.create_instance()
    m.migrate_disk()
