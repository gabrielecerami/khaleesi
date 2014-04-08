#! /usr/bin/env bash
set -e -u

export KHALEESI_SETTINGS_PATH=settings

./run.sh aio.yml \
    --build default \
    --tempest default \
    --settings-path ${KHALEESI_SETTINGS_PATH} \
    --site ${SITE:-'qeos'} \
    --installer packstack \
    --product rdo \
    --productreleaserepo production \
    --productrelease icehouse \
    --distribution rhel \
    --distrorelease "7.0" \
    --topology aio \
    --networking neutron \
    --variant default \
    --tags ${TAGS:-'provision,prep'} \
    --testsuite tempest

