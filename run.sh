#! /usr/bin/env bash
set -e -u

main() {
    local rdo_icehouse_f20_baseurl='http://repos.fedorapeople.org/repos/openstack/openstack-icehouse/fedora-20'
    local rdo_icehouse_epel6_baseurl='http://repos.fedorapeople.org/repos/openstack/openstack-icehouse/epel-6'
    local default_flavor_id=3
    local default_floating_nw_name='external'

    local key_file=${KEY_FILE:-testkkey.pem }
    local key_name=${SSH_KEY_NAME:-'testkey'}
    chmod 600 $key_file

    local node_prefix=${NODE_PREFIX:-gc}
    local image_id=${IMAGE_ID:-'cbf028d7-397c-4b2f-94b2-4b7f44e1936b'}
    local flavor_id=${FLAVOR_ID:-$default_flavor_id}
    local floating_nw_name=${FLOATING_NETWORK_NAME:-$default_floating_nw_name}
    local network_name=${NETWORK_NAME:-'default'}

    local baseurl=${REPO_BASEURL:-$rdo_icehouse_f20_baseurl}
    local net_1=${NET_1:-'0209ad36-6f76-4e97-a0d3-895bf100e7c2'}

    local tags=${TAGS:-''}
    local tempest_tests=${TEMPEST_TEST_NAME:-'tempest'}

cat > settings.yml <<-EOF
# job config

workarounds_disabled: yes
selinux: permissive  #[permissive, enforcing]

config:
  product: rdo
  version: icehouse
  repo: production
  verbosity:
    - info
    - warning

# OpenStack controller settings
os_auth_url: '$OS_AUTH_URL'
os_username: $OS_USERNAME
os_password: $OS_PASSWORD
os_tenant_name: $OS_TENANT_NAME

# instance settings
node_prefix: $node_prefix
network_ids: [{ net-id: '$net_1' }]
image_id: $image_id
ssh_private_key: $key_file
ssh_key_name: $key_name
flavor_id: $flavor_id
floating_network_name: $floating_nw_name

nodes:
  - name: "{{ node_prefix }}rdopkg"
    image_id: "{{ image_id }}"
    key_name: "{{ ssh_key_name }}"
    flavor_id: "{{ flavor_id }}"
    network_ids: "{{ network_ids }}"
    hostname: packstack.example.com
    groups: "RHEL,packstack,openstack_nodes"

#VM settings
rhel_os_repo: download.eng.bos.redhat.com/rel-eng/latest-RHEL-7/compose/Server/x86_64/os/
rhel_updates_repo: download.eng.bos.redhat.com/rel-eng/latest-RHEL-7/compose/Server/x86_64/os/
rhel_optional_repo: download.eng.bos.redhat.com/rel-eng/latest-RHEL-7/compose/Server/x86_64/os/
epel_repo: download.fedoraproject.org/pub/epel/beta/7/

gpg_check: 0
ntp_server: clock.redhat.com
reboot_delay: +1

# Currently sudo w/ NOPASSWD must be enabled in /etc/sudoers for sudo to work
sudo: yes
remote_user: fedora
#remote_user: cloud-user
sudo_user: root

tempest:
    puppet_file: /tmp/tempest_init.pp
    checkout_dir: /var/lib/tempest
    revision: 'stable/havana'
    test_name: $tempest_tests
    exclude:
        files:
            - test_server_rescue
            - test_server_actions
            - test_load_balancer
            - test_vpnaas_extensions
        tests:
            - test_rescue_unrescue_instance
            - test_create_get_delete_object
            - test_create_volume_from_snapshot
            - test_service_provider_list
            - test_ec2_
            - test_stack_crud_no_resources
            - test_stack_list_responds

EOF



### disabled since it is already in <git.root>/ansible.cfg
##export ANSIBLE_HOST_KEY_CHECKING=False
##export ANSIBLE_ROLES_PATH=$WORKSPACE/khaleesi/roles
##export ANSIBLE_LIBRARY=$WORKSPACE/khaleesi/library:$VIRTUAL_ENV/share/ansible

ansible-playbook -vvvvvv -i local_hosts  \
 playbooks/packstack/rdo_neutron_aio_playbook.yml \
    --extra-vars @settings.yml -v -u cloud-user $tags
}

main "$@"
