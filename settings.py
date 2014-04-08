#! /usr/bin/env python

import yaml
import os
import argparse
import sys
import urllib2
import stat
import copy
import string
#for debugging
import pprint
import logging

# not yet used
#from novaclient.v1_1 import client as os_novaclient


class KeyPathError(Exception):

    def __init__(self, keypath, details):
        self.keypath = keypath
        self.details = details

    def __str__(self):
        if self.keypath is None:
            return "Key path error: %s" % (self.details)
        else:
            return "Key path error in %s (%s) against data subtree %s: $s" % (
                self.keypath.keypath_string,
                self.keypath.match_depth_segment,
                pprint.pformat(self.keypath.pointer),
                self.details)


class KeyPath(object):

    def __init__(self, keypath_fullstring, values=None, select_function=None):
        if keypath_fullstring is None:
            raise KeyPathError(None, "Null keypath string")
        self.keypath_string = keypath_fullstring.split('=')[0]
        self.keypathlist = self.keypath_string.split('.')
        # replace all : with .
        self.keypathlist = map(string.replace,
                               self.keypathlist,
                               (':')*len(self.keypathlist),
                               ('.')*len(self.keypathlist))
        # The override function get a tuple of
        # values and returns a single value that may or may be not
        # one of the values of the tuple
        self.select_function = select_function

        try:
            stringvalue = keypath_fullstring.split('=')[1]
        except IndexError:
            stringvalue = None

        if stringvalue and values:
            raise Exception("Values for keypath can be specified either by string or value parameter, but not both")
        if stringvalue:
            self.value = stringvalue

        self.set_value(values)

        self.match_depth = None
        self.match_depth_segment = None
        self.path_match = False
        self.value_match = False
        self.parentpointer = None
        self.pointer = None

    def set_value(self, values):
        if type(values) is tuple:
            if self.select_function:
                self.value = self.select_function(*values)
            else:
                self.value = None
        else:
            self.value =  values

    def search_in(self, data):
        """
        search for keypath inside a mixed dict/list data structure
        keypath is navigated and compared against the data.
        match_depth records the position of the last key matching the data
        if all keypath is matched, path_match is set to True then value is compared too if specified
        pointer contains a pointer to data referenced by the last key in keypath
        parentpointer contains a pointer to the upper level data structure
        """

        self.parentpointer = data
        self.pointer = data
        for index, segment in enumerate(self.keypathlist):
            tmppointer = self.parentpointer
            self.parentpointer = self.pointer

            if type(self.pointer) is dict:
                try:
                    self.pointer = self.pointer[segment]
                except KeyError:
                    self.parentpointer = tmppointer
                    return
            elif type(self.pointer) is list:
                try:
                    self.pointer = self.pointer[int(segment)]
                except (TypeError, IndexError):
                    self.parentpointer = tmppointer
                    return

            self.match_depth = index
            self.match_depth_segment = segment

        self.path_match = True
        if self.value:
            self.value_match = (self.value == self.pointer)

    def structurize(self, depth):
        """
        converts keypath starting from "depth" position
        to a mixed dict/list data structure
        from a.b.c=value to {'a': {'b': {'c': 'value'}}}
        from a.0.c=value to {'a': [{'c': 'value'}]}
        """
        # TODO: it should be more readable and simpler implementing
        # this function recursively
        rgrow_dict = self.value
        tmp_keypathlist = copy.deepcopy(self.keypathlist)
        while tmp_keypathlist[depth:]:
            try:
                tmp_dataroot = tmp_keypathlist[-2]
            except IndexError:
                tmp_dataroot = 'temporarydataroot'
            if len(tmp_keypathlist) == 1:
                index = 0
            else:
                index = -1
            try:
                key = int(tmp_keypathlist[index])
            except ValueError:
                key = tmp_keypathlist[index]
            if type(key) is int:
                locals()[tmp_dataroot] = []
                locals()[tmp_dataroot].append(rgrow_dict)
            elif type(key) is str:
                locals()[tmp_dataroot] = {}
                locals()[tmp_dataroot][key] = rgrow_dict
            rgrow_dict = locals()[tmp_dataroot]
            tmp_keypathlist.pop()

        return rgrow_dict


class Settings(object):

    def __init__(self, data, select_function=None):
        """
        keypath is a class composed by a string that defines a
        list of keys and optionally an assigned value, and a mixed dict/list data
        structure
        key may be string or integers
        Ex. "a.b.c=0"

        string keys refer to dict parts of the data structure
        integer keys refer to list parts of the data structure
        """
        self.data = data
        self.keypaths = {}
        self.keypath_max = 10
        if select_function:
            self.select_function = select_function

    def set_select_function(self, select_function):
        self.select_function = select_function

    def add_keypath(self, keypath_string, values):

        if keypath_string not in self.keypaths:
            keypath = KeyPath(keypath_string, values=values, select_function=self.select_function)
            # ugly garbage collection
            # since python 2.6 does not support orderedDict a random key will
            # be deleted
            if len(self.keypaths) > self.keypath_max:
                self.keypaths.popitem()
            self.keypaths[keypath_string] = keypath
        elif self.keypaths[keypath_string].value != values:
            self.keypaths[keypath_string].set_value(values)
        self.keypaths[keypath_string].search_in(self.data)

        return self.keypaths[keypath_string]

    def delete(self, keypath_string, values=None):
        keypath = self.add_keypath(keypath_string, values)

        if keypath.path_match:
            if keypath.value is not None:
                if not keypath.value_match:
                    raise KeyPathError(self.keypath, "Specified value does not match")
            overstructure = keypath.parentpointer
            if type(overstructure) is list:
                key = keypath.keypathlist[int(keypath.match_depth)]
            elif type(overstructure) is dict:
                key = keypath.keypathlist[keypath.match_depth]

            overstructure.pop(key)

    # XXX: if values is None (no values could be chosen from the tuple), do not perform any operation
    def create(self, keypath_string, values=None):
        keypath = self.add_keypath(keypath_string, values)

        overstructure = keypath.parentpointer
        if keypath.path_match:
            raise KeyPathError(keypath, "path already exists")
        else:
            if keypath.match_depth is None:
                # Keypath did not matched from root, structurize everything
                new_data = keypath.structurize(0)
                key = keypath.keypathlist[0]
                if type(overstructure) is dict:
                        overstructure.update(new_data)
                elif type(overstructure) is list:
                        overstructure.append(new_data)
            else:
                # Structurize everythin past last matched key
                new_data = keypath.structurize(keypath.match_depth + 1)
                key = keypath.keypathlist[keypath.match_depth]
                if type(overstructure) is dict:
                        overstructure[key].update(new_data)
                elif type(overstructure) is list:
                        overstructure[key].append(new_data)

    def update(self, keypath_string, values=None):
        keypath = self.add_keypath(keypath_string, values)
        print "updating " + keypath_string + " with value " + str(keypath.value)
        pprint.pprint(keypath.pointer)
        if not keypath.path_match:
            raise KeyPathError(keypath, "path does not exist")
        elif keypath.value_match:
            logging.warning("%s does not need update" % (keypath.keypath_string))
        else:
            overstructure = keypath.parentpointer
            new_data = keypath.structurize(keypath.match_depth)
            key = keypath.keypathlist[keypath.match_depth]
            print key
            print overstructure[key]
            if type(overstructure) is dict:
                    overstructure.update(new_data)
            elif type(overstructure) is list:
                    overstructure.append(new_data)

    def set(self, keypath_string, values=None):
        keypath = self.add_keypath(keypath_string, values)

        if keypath.path_match:
            self.update(keypath_string, values)
        else:
            self.create(keypath_string, values)

    def fetch(self, keypath_string, values=None):
        keypath = self.add_keypath(keypath_string, values)

        # value will be ignored
        if keypath.value:
            logging.warning("specified value will be ignored")
        if keypath.path_match:
            return keypath.pointer
        else:
            raise KeyPathError(self, "path does not exist")

    def batch_execute(self, keypaths, operation):
        """
        Executes operation on a dict or list of keypaths
        in dict: keypath string as key, values as values.
        in list: keypath full string is required as value
        example
            settings.batch_execute({ "keypath": value}, operation)
        """
        if type(keypaths) is dict:
            for keypath_string in keypaths:
                values = keypaths[keypath_string]
                self.__getattribute__(operation)(keypath_string, values=values)
        elif type(keypaths) is list:
            for keypath_string in keypaths:
                self.__getattribute__(operation)(keypath_string)


class Job(object):

    _node_prefix_map = {
        "installer": {
            "foreman": "fore",
            "packstack": "pack",
            "tripleo": "trio"
        },
        "product": {
            "rdo": "rdo",
            "rhos": "rhos",
        },
        "productrelease": {
            "icehouse": "I",
            "havana": "H",
            "grizzly": "G",
        },
        "productreleaserepo": {
            "production": "prod",
            "stage": "sta",
            "testing": "test",
        },
        "distribution": {
            "centos": "C",
            "rhel": "R",
            "fedora": "F"
        },
        "distrorelease": {},
        "topology": {
            "aio": "a",
            "multinode": "m",
        },
        "networking": {
            "nova": "nova",
            "neutron": "neut",
            "ml2": "ml2",
        },
        "variant": {},
        "testsuite": {},
    }

    def generate_node_prefix(self, config):
        node_prefix = "{installer}-{product}-{productrelease}-{productreleaserepo}-{distribution}{distroversion}-{topology}-{networking}-{variant}".format(
            installer=self._node_prefix_map['installer'][config['installer']],
            product=self._node_prefix_map['product'][config['product']],
            productrelease=self._node_prefix_map['productrelease'][config['productrelease']],
            productreleaserepo=self._node_prefix_map['productreleaserepo'][config['productreleaserepo']],
            distribution=self._node_prefix_map['distribution'][config['distribution']],
            distroversion=config['distrorelease'].replace('.', ''),
            topology=self._node_prefix_map['topology'][config['topology']],
            networking=self._node_prefix_map['networking'][config['networking']],
            variant=config['variant'],
        )
        return node_prefix

    def get_value(self, env_var_name, cli_var_name, keypath_string):
        """
        Get value for a keypath in this order
        - specific command line argument
        - environment variable
        - value from a specified keypath
        - None
        Value can then be overriden by a generic --var-{set,update,create,delete} cli arg
        """
        try:
            return self.args_parsed.__dict__[cli_var_name]
        except KeyError:
            pass
        try:
            return os.environ[env_var_name]
        except KeyError:
            pass
        try:
            return self.settings.fetch(keypath_string)
        except KeyPathError:
            pass
        return None

    def __init__(self, args_parsed):
        self.args_parsed = args_parsed

        self.settings = Settings({}, select_function=self.get_value)
        self.settings.create('provision_site', values=('SITE', 'site', None))
        self.settings.create('job_name', values=('JOB_NAME', 'job_name', None))

        job_name = self.settings.fetch('job_name')

        if job_name is not None:
            job_name = job_name.split('_')
            job_name.reverse()
            keypaths = {
                'config.installer': job_name.pop(),
                'config.product': job_name.pop(),
                'config.productrelease': job_name.pop(),
                'config.productreleaserepo': job_name.pop().replace('-repo', ''),
                'config.distribution': job_name.pop(),
                'config.distrorelease': job_name.pop(),
                'config.topology': job_name.pop(),
                'config.networking': job_name.pop(),
                'config.variant': job_name.pop().replate('-variant', ''),
                'config.testsuite': job_name.pop().replace('-tests', ''),
            }
            self.settings.batch_execute(keypaths, 'create')

        self.settings_path = self.get_value('SETTINGS_PATH', 'settings_path', None)

        # No defaults are possible for site

        build_settings_path = "%s%sbuilds%s%s.yml" % (
            self.settings_path, os.sep, os.sep, 'defaults')
        try:
            with open(build_settings_path) as build_settings_file:
                self.settings.create('build', values=yaml.load(build_settings_file))
        except IOError:
            pass

        tempest_settings_path = "%s%stempest%s%s.yml" % (
            self.settings_path, os.sep, os.sep, 'defaults')
        try:
            with open(tempest_settings_path) as tempest_settings_file:
                self.settings.create('tempest', values=yaml.load(tempest_settings_file))
        except IOError:
            pass


class Build(object):

    def __init__(self, job, args):
        self.job = job
        self.args_parsed = args

        settingsdata = copy.deepcopy(job.settings.data)
        self.settings = Settings(settingsdata, select_function=self.get_value)
        # Hack, updating settings with job.settings section values
        # SHOULD NOT be needed in deepened settings.yml
        # future version of settings should only require
        # self.settings = copy.deepcopy(job.settings)

        try:
            builddata = job.settings.fetch('build')
            self.settings.data.update(builddata)
        except KeyPathError:
            pass

        keypaths = {
            'config.installer': ('INSTALLER', 'installer', 'config.installer'),
            'config.product': ('PRODUCT', 'product', None),
            'config.productrelease': ('PRODUCTRELEASE', 'productrelease', None),
            'config.productreleaserepo': ('PRODUCTRELEASEREPO', 'productreleaserepo', None),
            'config.distribution': ('DISTRIBUTION', 'distribution', 'config.distribution'),
            'config.distrorelease': ('DISTRORELEASE', 'distrorelease', 'config.distrorelease'),
            'config.topology': ('TOPOLOGY', 'topology', 'config.topology'),
            'config.networking': ('NETWORKING', 'networking', 'config.networking'),
            'config.variant': ('VARIANT', 'variant', 'config.variant'),
            'config.testsuite': ('TESTS', 'testsuite', 'config.testsuite'),

            # for backwards compatibility
            'config.netplugin': ('NETPLUGIN', 'networking', None),
            'config.version': ('PRODUCTRELEASE', 'productrelease', None),
            'config.repo': ('PRODUCTRELEASEREPO', 'productreleaserepo', None),
        }
        self.settings.batch_execute(keypaths, 'set')

        self.site_settings_filename = self.settings.fetch('provision_site')
        self.tempest_settings_filename = self.settings.fetch('config.testsuite')
        self.build_settings_filename = self.settings.fetch('config.variant')

        # load build specific conf
        site_settings_path = "%s%ssites%s%s.yml" % (
            self.job.settings_path, os.sep, os.sep, self.site_settings_filename)
        try:
            with open(site_settings_path) as site_settings_file:
                self.settings.set('site', values=yaml.load(site_settings_file))
        except IOError:
            pass

        build_settings_path = "%s%sbuilds%s%s.yml" % (
            self.job.settings_path, os.sep, os.sep, self.build_settings_filename)
        try:
            with open(build_settings_path) as build_settings_file:
                self.settings.set('build', values=yaml.load(build_settings_file))
        except IOError:
            pass

        tempest_settings_path = "%s%stempest%s%s.yml" % (
            self.job.settings_path, os.sep, os.sep, self.tempest_settings_filename)
        try:
            with open(tempest_settings_path) as tempest_settings_file:
                self.settings.set('tempest', values=yaml.load(tempest_settings_file))
        except IOError:
            pass

    def generate_settings(self):
        distribution = self.settings.fetch('config.distribution')
        distrorelease = self.settings.fetch('config.distrorelease').replace('.', ':')
        product = self.settings.fetch('config.product')
        productrelease = self.settings.fetch('config.distrorelease').replace('.', ':')

        fetch = self.settings.fetch('site.images.centos.6:5.id')
        print "FETCH " + fetch
        keypaths = {
            'packstack_int': 'whayutin',
            'config.verbosity': ['info', ],

            'os_auth_url': ('OS_AUTH_URL', None, 'site.controller.auth-url'),
            'os_username': ('OS_USERNAME', None, 'site.controller.username'),
            'os_password': ('OS_PASSWORD', None, 'site.controller.password'),
            'os_tenant_name': ('OS_TENANT_NAME', None, 'site.controller.tenant_name'),
            'os_network_type': ('OS_NETWORK_TYPE', None, 'site.controller.network-type'),

            # instance settings
            'image_id': ('IMAGE_ID', None, 'site.images.' + distribution + '.' + distrorelease + '.id'),
            'remote_user': ('REMOTE_USER', None, 'site.images.' + distribution + '.' + distrorelease + '.remote-user'),
            'ssh_private_key': ('KEY_FILE', None, 'site.instances.key_filename'),
            'ssh_private_key_remote': ('KEY_FILE_REMOTE', None, 'site.instances.key_remote_url'),
            'ssh_key_name': ('KEY_NAME', None, 'site.instances.key_name'),
            'flavor_id': ('FLAVOR_ID', None, 'site.instances.flavors.default.id'),
            'flavor_name': ('FLAVOR_NAME', None, 'site.instances.flavors.default.name'),
            'floating_network_name': ('FLOATING_NETWORK_NAME', None, 'site.networks.floating.name'),
            'tempest_image_id': ('TEMPEST_IMAGE_ID', None, 'site.images.tempest.id'),
            'tempest_flavor_id': ('TEMPEST_FLAVOR_ID', None, 'site.instances.flavors.tempest.id'),
            'tempest_flavor_name': ('TEMPEST_FLAVOR_NAME', None, 'site.instances.flavors.tempest.name'),
            'tempest_remote_user': ('TEMPEST_REMOTE_USER', None, 'site.images.tempest.remote-user'),
            'foreman_image_id': ('FOREMAN_IMAGE_ID', None, 'site.images.foreman.id'),
            'foreman_flavor_id': ('FOREMAN_FLAVOR_ID', None, 'site.instances.flavors.foreman.id'),
            'foreman_flavor_name': ('FOREMAN_FLAVOR_NAME', None, 'site.instances.flavors.foreman.name'),
            'foreman_remote_user': ('FOREMAN_REMOTE_USER', None, 'site.images.foreman.remote-user'),
            # tempest overrides
            'tempest.revision': (None, None ,'tempest.revisions.' + product + '.'+ productrelease),
            'tempest.tempest_test_name' : ('TEMPEST_TEST_NAME', None, 'tempest.test_name'),
        }
        self.settings.batch_execute(keypaths, 'create')
        keypaths = {
            # build overrides
            'node_prefix': ('NODE_PREFIX', None, 'node_prefix'),
            'wait_for_boot': ('WAIT_FOR_BOOT', None, 'build.wait_for_boot'),
            'update_rpms_tarball': ('UPDATE_RPMS_TARBALL', None, 'build.update_rpms_tarball'),
            'selinux': ('SELINUX', None, 'selinux')
        }
        self.settings.batch_execute(keypaths, 'set')
        # More network settings
        #
        # we can use novaclient to check id->name translation
        #novaclient = os_novaclient.Client(os_username, os_password, os_tenant_name, os_auth_url, service_type='compute')
        #net = novaclient.networks.find(id=network['id'])
        #net_names.append(net.label)
        network_ids = []
        network_names = []
        for seq, network in enumerate(self.settings.fetch('site.networks.internal')):
            # skip net 0
            if seq != 0:
                self.settings.create('net_' + str(seq) + '_name', values=('NET_' + str(seq) + '_NAME',  None, 'site.networks.internal.' + str(seq) + '.name'))
                network_names.append(self.settings.fetch('net_' + str(seq) + '_name'))
                network_ids.append({'net-id': os.getenv('NET_' + str(seq),  network['id'])})
        self.settings.create('network_ids', values=network_ids)
        self.settings.create('network_names', values=network_names)

        node_prefix = self.job.generate_node_prefix(self.settings.fetch('config'))
        self.settings.update('node_prefix', values=node_prefix)
        pprint.pprint(self.settings.data)
        # Final overrides
        # cli generic manipulation parameters (set,delete,create,update)
        # have priority over all other way of retrieveing settings
        if self.args_parsed.set_variables:
            self.settings.batch_execute(set_variables, 'set')
        if self.args_parsed.delete_variables:
            self.settings.batch_execute(set_variables, 'delete')
        if self.args_parsed.create_variables:
            self.settings.batch_execute(set_variables, 'create')
        if self.args_parsed.update_variables:
            self.settings.batch_execute(set_variables, 'update')

        # Cleanup
        # remove tempest revision mappings
        self.settings.delete('tempest.revisions')
        # needed by the previous hacks
        self.settings.delete('build')
        self.settings.delete('site')

    def get_value(self, env_var_name, cli_var_name, keypath_string):
        """
        Get value for a keypath in this order
        - specific command line argument
        - environment variable
        - value from a specified keypath
        - None
        Value can then be overriden by a generic --var-{set,update,create,delete} cli arg
        """
        try:
            return self.args_parsed.__dict__[cli_var_name]
        except KeyError:
            pass
        try:
            return os.environ[env_var_name]
        except KeyError:
            pass
        try:
            return self.settings.fetch(keypath_string)
        except KeyPathError:
            pass
        return None

    def retrieve_key_file(self):
        url = self.settings.fetch('ssh_private_key_remote')
        key_filename = self.settings.fetch('ssh_private_key')
        if url:
            response = urllib2.urlopen(url)
            key = response.read()
            with open(key_filename, "w") as key_file:
                key_file.write(key)
            os.chmod(key_filename, stat.S_IRUSR | stat.S_IWUSR)

    def write_settings(self, output_settings_path):
        with open(output_settings_path, "w") as output_settings_file:
            output_settings_file.write("# job config\n")
            output_settings_file.write(yaml.safe_dump(self.settings.data,
                                                 default_flow_style=False))


def parse_args(args):
    parser = argparse.ArgumentParser(description="Load khaleesi build settings")
    parser.add_argument("--job-name",
                        dest="job_name",
                        help="",)
    parser.add_argument("-o", "--output-settings",
                        dest="output_settings_path",
                        required=True,
                        help="Path for the output settings")
    parser.add_argument("-s", "--site",
                        dest="site",
                        required=True,
                        help="Site where the build is launched")
    parser.add_argument("-P", "--settings-path",
                        dest="settings_path",
                        required=True,
                        default="../khaleesi-settings",
                        help="The path where khaleesi settings are")
    parser.add_argument("--product",
                        dest="product",
                        help="",)
    parser.add_argument("--productrelease",
                        dest="productrelease",
                        help="")
    parser.add_argument("--productreleaserepo",
                        dest="productreleaserepo",
                        help="",)
    parser.add_argument("--installer",
                        dest="installer",
                        help="",)
    parser.add_argument("--distribution",
                        dest="distribution",
                        help="",)
    parser.add_argument("--distrorelease",
                        dest="distrorelease",
                        help="",)
    parser.add_argument("--topology",
                        dest="topology",
                        help="",)
    parser.add_argument("--networking",
                        dest="networking",
                        help="",)
    parser.add_argument("--variant",
                        dest="variant",
                        help="",)
    parser.add_argument("--testsuite",
                        dest="testsuite",
                        help="",)
    parser.add_argument("--ignore-parameters-from",
                        dest="ignore_from",
                        help="",)
    parser.add_argument("--set-variable",
                        action='append',
                        dest="set_variables",
                        help="",)
    parser.add_argument("--delete-variable",
                        action='append',
                        dest="delete_variables",
                        help="",)
    parser.add_argument("--update-variable",
                        action='append',
                        dest="update_variables",
                        help="",)
    parser.add_argument("--create-variable",
                        action='append',
                        dest="create_variables",
                        help="",)
    args_parsed, unknown = parser.parse_known_args(args)

    return args_parsed


def setup_logging():
    logger = logging.getLogger('settings')
    logger.setLevel(logging.DEBUG)

    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)

    formatter = logging.Formatter('%(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    return logger


def main(args):
    logger = setup_logging()
    args_parsed = parse_args(args)

    current_job = Job(args_parsed)

    # colors:
    #  print "\033[3" + str(number) + ";1m" + string

    current_build = Build(current_job, args_parsed)
    current_build.generate_settings()
    current_build.retrieve_key_file()
    current_build.write_settings(args_parsed.output_settings_path)

if __name__ == '__main__':
    main(sys.argv)
