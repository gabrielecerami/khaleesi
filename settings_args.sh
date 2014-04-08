#! /usr/bin/env bash
set -e -x
main() {

settings_args=" --output-settings settings.yml "
playbook=aio.yml

set +e
while [[ "x$1" != "x" ]]
do
    case $1 in
        --settings-path)
            settings_path=$2
            settings_args+=" $1 $2 "
            shift 2
            ;;
        --build)
            build=$2
            settings_args+=" $1 $2 "
            shift 2
            ;;
        --tempest)
            tempest=$2
            settings_args+=" $1 $2 "
            shift 2
            ;;
        --site)
            site=$2
            settings_args+=" $1 $2 "
            shift 2
            ;;
        --installer)
            installer=$2
            settings_args+=" $1 $2 "
            shift 2
            ;;
        --product)
            product=$2
            settings_args+=" $1 $2 "
            shift 2
            ;;
        --productreleaserepo)
            productreleaserepo=$2
            settings_args+=" $1 $2 "
            shift 2
            ;;
        --productrelease)
            productrelease=$2
            settings_args+=" $1 $2 "
            shift 2
            ;;
        --distribution)
            distribution=$2
            settings_args+=" $1 $2 "
            shift 2
            ;;
        --distrorelease)
            distrorelese=$2
            settings_args+=" $1 $2 "
            shift 2
            ;;
        --topology)
            topology=$2
            settings_args+=" $1 $2 "
            shift 2
            ;;
        --networking)
            networking=$2
            settings_args+=" $1 $2 "
            shift 2
            ;;
        --variant)
            variant=$2
            settings_args+=" $1 $2 "
            shift 2
            ;;
        --testsuite)
            testsuite=$2
            settings_args+=" $1 $2 "
            shift 2
            ;;
        --tags)
            tags=$2
            settings_args+=" $1 $2 "
            shift 2
            ;;
        --skip-tags)
            skip_tags=$2
            settings_args+=" $1 $2 "
            shift 2
            ;;
        -I|--inventory)
            inventory_file=$2
            shift 2
            ;;
        -P|--playbook)
            playbook=$2
            shift 2
            ;;
        -*)
            printf >&2 "Unknown Option: %s\n $1"
            shift
            ;;
        *.yml)
            # backwards compatibility, may harvest spurious data
            playbook=$1
            shift
            ;;
        *)
            echo "Parser reached end of known arguments"
            break
            ;;
    esac
done
set -e

# If the playbook does NOT contain a '/', default to the packstack playbooks
if [[ $(expr index "$playbook" /) -eq 0 ]]; then
playbook="playbooks/packstack/$playbook"
fi
echo "Playbook=$playbook"

if [[ ! -e settings.yml ]]; then
    echo "settings arguments $settings_args"
    python settings.py $settings_args
fi

cmdline=" --extra-vars @settings.yml --extra-vars @nodes.yml"

if [[ -e repo_settings.yml ]]; then
    cmdline+=" --extra-vars @repo_settings.yml "
fi

#if [[ -e job_settings.yml ]]; then
#    cmdline+=" --extra-vars @job_settings.yml "
#fi

#if [[ ! -iz $remote_user ]]; then
#   cmdline+=" -u $remote_user -s"
#fi
cmdline+=" -u root -s"

if [[ ! -z $tags ]]; then
  # Remove extraneous '--tags' first. Jobs that use this should switch to just
  # providing the tags
  tags=${tags#--tags=}
  cmdline+=" --tags $tags"
fi

if [[ ! -z $inventory_file  ]]; then
    true
#    if [[ ! -z $skip_tags ]]; then
#      skip_tags+=",provision"
#    else
#      skip_tags="provision"
#    fi
else
    inventory_file="local_hosts"
    cmdline+=" --extra-vars @nodes.yml"
fi

if [[ ! -z $skip_tags ]]; then
  # Same as tags
  skip_tags=${skip_tags#--skip_tags}
  cmdline+=" --skip-tags $skip_tags"
fi

cmdline+=" -i $inventory_file "

local khaleesi_verbose=${KHALEESI_VERBOSE:-false}
local khaleesi_ssh_verbose=${KHALEESI_SSH_VERBOSE:-false}
if $khaleesi_verbose || $khaleesi_ssh_verbose; then
cmdline+=" -v"
  if $khaleesi_ssh_verbose; then
cmdline+="vvv"
  fi
fi

echo "Execute Command:"
echo "$cmdline"
echo " settings = $cmdline"
echo "playbook = $playbook"

ansible-playbook $playbook $cmdline --extra-vars @job_settings.yml

#need a zero exit everytime so teardown can be executed
return 0

}

collect_logs() {

  if [[ ! -z $skip_tags_collect ]]; then
    skip_tags=${skip_tags_collect#--skip_tags}
    cmdline+=" --skip-tags $skip_tags_collect"
  fi
  echo "Execute Command:"
  echo "$cmdline"
  ansible-playbook playbooks/collect_logs.yml $cmdline

}

if [ ! -e nodes.yml ]; then
  echo "Please create a nodes.yml file to define your environment"
  echo "See https://github.com/redhat-openstack/khaleesi/blob/master/doc/packstack.md"
  exit 1
fi

# requires a 0 exit code for clean.sh to execute
main "$@" || true
collect_logs || true

