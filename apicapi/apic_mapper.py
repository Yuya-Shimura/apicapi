# Copyright (c) 2014 Cisco Systems Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
#
# @author: Mandeep Dhami (dhami@noironetworks.com), Cisco Systems Inc.

import re

import contextlib

LOG = None


NAMING_STRATEGY_UUID = 'use_uuid'
NAMING_STRATEGY_NAMES = 'use_name'
NAME_TYPE_TENANT = 'tenant'
NAME_TYPE_NETWORK = 'network'
NAME_TYPE_SUBNET = 'subnet'
NAME_TYPE_PORT = 'port'
NAME_TYPE_ROUTER = 'router'
NAME_TYPE_APP_PROFILE = 'app-profile'
NAME_TYPE_POLICY_TARGET_GROUP = 'policy_target_group'
NAME_TYPE_L3_POLICY = 'l3_policy'
NAME_TYPE_L2_POLICY = 'l2_policy'
NAME_TYPE_POLICY_RULE_SET = 'policy_rule_set'
NAME_TYPE_POLICY_RULE = 'policy_rule'

MAX_APIC_NAME_LENGTH = 46


@contextlib.contextmanager
def mapper_context(context):
    if context and (not hasattr(context, '_plugin_context') or
                    context._plugin_context is None):
        context._plugin_context = context  # temporary circular reference
        yield context
        context._plugin_context = None     # break circular reference
    else:
        yield context


def truncate(string, max_length):
    if max_length < 0:
        return ''
    return string[:max_length] if len(string) > max_length else string


class APICNameMapper(object):
    def __init__(self, db, log, keyclient, keystone_authtoken,
                 strategy=NAMING_STRATEGY_UUID):
        self.db = db
        self.strategy = strategy
        self.keystone = None
        self.keyclient = keyclient
        self.keystone_authtoken = keystone_authtoken
        self.tenants = {}
        global LOG
        LOG = log.getLogger(__name__)

    def mapper(name_type):
        """Wrapper to land all the common operations between mappers."""
        def wrap(func):
            def inner(inst, context, resource_id, remap=False):
                if remap:
                    inst.db.delete_apic_name(resource_id)
                else:
                    saved_name = inst.db.get_apic_name(resource_id,
                                                       name_type)
                    if saved_name:
                        return ApicName(saved_name[0], resource_id, context,
                                        inst, func.__name__)
                try:
                    name = func(inst, context, resource_id)
                except Exception:
                    LOG.exception(("Exception in looking up name %s"),
                                  name_type)
                    raise

                result = re.sub(r"-+", "-", resource_id)
                if name:
                    name = re.sub(r"-+", "-", name)
                    if inst.strategy == NAMING_STRATEGY_NAMES:
                        result = name
                    elif inst.strategy == NAMING_STRATEGY_UUID:
                        # Keep as many uuid chars as possible
                        id_suffix = "_" + result
                        max_name_length = MAX_APIC_NAME_LENGTH - len(id_suffix)
                        result = truncate(name, max_name_length) + id_suffix

                result = truncate(result, MAX_APIC_NAME_LENGTH)
                inst.db.update_apic_name(resource_id, name_type, result)
                return ApicName(result, resource_id, context, inst,
                                func.__name__)
            return inner
        return wrap

    @mapper(NAME_TYPE_TENANT)
    def tenant(self, context, tenant_id):
        tenant_name = None
        if tenant_id in self.tenants:
            tenant_name = self.tenants.get(tenant_id)
        else:
            if self.keystone is None:
                keystone_conf = self.keystone_authtoken
                auth_url = ('%s://%s:%s/v2.0/' % (
                    keystone_conf.auth_protocol,
                    keystone_conf.auth_host,
                    keystone_conf.auth_port))
                username = keystone_conf.admin_user
                password = keystone_conf.admin_password
                project_name = keystone_conf.admin_tenant_name
                self.keystone = self.keyclient.Client(
                    auth_url=auth_url,
                    username=username,
                    password=password,
                    tenant_name=project_name)
            for tenant in self.keystone.tenants.list():
                self.tenants[tenant.id] = tenant.name
                if tenant.id == tenant_id:
                    tenant_name = tenant.name
        return tenant_name

    @mapper(NAME_TYPE_NETWORK)
    def network(self, context, network_id):
        network = context._plugin.get_network(
            context._plugin_context, network_id)
        network_name = network['name']
        return network_name

    @mapper(NAME_TYPE_SUBNET)
    def subnet(self, context, subnet_id):
        subnet = context._plugin.get_subnet(context._plugin_context, subnet_id)
        subnet_name = subnet['name']
        return subnet_name

    @mapper(NAME_TYPE_PORT)
    def port(self, context, port_id):
        port = context._plugin.get_port(context._plugin_context, port_id)
        port_name = port['name']
        return port_name

    @mapper(NAME_TYPE_ROUTER)
    def router(self, context, router_id):
        return context._plugin_context.session.execute(
            'SELECT * from routers WHERE id = :id',
            {'id': router_id}).fetchone().name

    @mapper(NAME_TYPE_POLICY_TARGET_GROUP)
    def policy_target_group(self, context, policy_target_group_id):
        epg = context._plugin.get_policy_target_group(context._plugin_context,
                                                 policy_target_group_id)
        return epg['name']

    @mapper(NAME_TYPE_L3_POLICY)
    def l3_policy(self, context, l3_policy_id):
        l3_policy = context._plugin.get_l3_policy(context._plugin_context,
                                                  l3_policy_id)
        return l3_policy['name']

    @mapper(NAME_TYPE_L3_POLICY)
    def l2_policy(self, context, l2_policy_id):
        l2_policy = context._plugin.get_l2_policy(context._plugin_context,
                                                  l2_policy_id)
        return l2_policy['name']

    @mapper(NAME_TYPE_POLICY_RULE_SET)
    def policy_rule_set(self, context, policy_rule_set_id):
        policy_rule_set = context._plugin.get_policy_rule_set(
            context._plugin_context, policy_rule_set_id)
        return policy_rule_set['name']

    @mapper(NAME_TYPE_POLICY_RULE)
    def policy_rule(self, context, policy_rule_id):
        policy_rule = context._plugin.get_policy_rule(context._plugin_context,
                                                      policy_rule_id)
        return policy_rule['name']

    def app_profile(self, context, app_profile, remap=False):
        if remap:
            self.db.delete_apic_name('app_profile')
        # Check if a profile is already been used
        saved_name = self.db.get_apic_name('app_profile',
                                           NAME_TYPE_APP_PROFILE)
        if not saved_name:
            self.db.update_apic_name('app_profile', NAME_TYPE_APP_PROFILE,
                                     app_profile)
            result = app_profile
        else:
            result = saved_name[0]
        return ApicName(result, app_profile, None,
                        self, self.app_profile.__name__)


class ApicName(object):

    def __init__(self, mapped, uid='', context=None, inst=None, fname=''):
        self.uid = uid
        self.context = context
        self.inst = inst
        self.fname = fname
        self.value = mapped

    def renew(self):
        if self.uid and self.inst and self.fname:
            # temporary circular reference
            with mapper_context(self.context) as ctx:
                result = getattr(self.inst, self.fname)(ctx, self.uid,
                                                        remap=True)
            self.value = result.value
            return self

    def __str__(self):
        return self.value