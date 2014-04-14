#! /usr/bin/env bash
set -e -u
source functions.bash

collect_logs() {
  local cmdline="ansible-playbook -v -i local_hosts  \
             playbooks/collect_logs.yml \
             --extra-vars @settings.yml   \
             --extra-vars @nodes.yml "

  [[ -n ${REMOTE_USER:-''} ]] && cmdline+=" -u $REMOTE_USER -s"
  [[ -n ${SKIP_TAGS:-''} ]] && cmdline+=" --skip-tags ${SKIP_TAGS#--skip_tags}"

  execute $cmdline
}

cat_file() {
    echo "----- [ $1 ]---------------------------------------"
    cat $1
    echo "---------------------------------------------------"
}

main() {
    if [ ! -e nodes.yml ]; then
        echo "Please create a nodes.yml file to define your environment"
        echo "See https://github.com/redhat-openstack/khaleesi/blob/master/doc/packstack.md"
        return 1
    fi

    local default_playbook='aio.yml'

    parse_settings_args "$@"
    PLAYBOOK=${PLAYBOOK:-$default_playbook}
    INVENTORY_FILE=${INVENTORY_FILE:-local_hosts}

    # If the playbook does NOT contain a '/', default to the packstack playbooks
    [[ $PLAYBOOK =~ '/' ]] ||  PLAYBOOK="playbooks/packstack/$PLAYBOOK"
    echo "Playing: $PLAYBOOK"

    execute python settings.py $settings_args \
        -o settings.yml


    echo -n "settings: settings.yml"
    ### todo: add  --no-color option
    export ANSIBLE_FORCE_COLOR=true
    local cmdline="ansible-playbook -v -i ${INVENTORY_FILE} $PLAYBOOK -s  \
                   --extra-vars @settings.yml "

    if [[ -e repo_settings.yml ]]; then
        echo -n ", repo_settings.yml"
        cmdline+=" --extra-vars @repo_settings.yml"
    fi

    if  [[ -e job_settings.yml ]]; then
        echo -n ", job_settings.yml"
        cmdline+=" --extra-vars @job_settings.yml"
    fi
    echo
    cmdline+=" --extra-vars @nodes.yml"

    cat_file settings.yml
    test -e repo_settings.yml && cat_file repo_settings.yml
    test -e job_settings.yml  && cat_file job_settings.yml

    # tags and skip tags
    # Remove extraneous '--tags' first.
    #Jobs that use this should switch to just providing the tags
    [[ -n ${TAGS:-''} ]] && cmdline+=" --tags ${TAGS#--tags=}"
    [[ -n ${SKIP_TAGS:-''} ]] && cmdline+=" --skip-tags ${SKIP_TAGS#--skip_tags}"

    local khaleesi_verbose=${KHALEESI_VERBOSE:-false}
    local khaleesi_ssh_verbose=${KHALEESI_SSH_VERBOSE:-false}
    if $khaleesi_verbose || $khaleesi_ssh_verbose; then
        cmdline+=" -v"
        $khaleesi_ssh_verbose && cmdline+="vvv"
    fi

    # collect logs only if the settings are proper
    on_exit collect_logs
    execute $cmdline
}

# requires a 0 exit code for clean.sh to execute
on_exit init.print_result
main "$@" || true

