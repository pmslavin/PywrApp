""" Module to generate a Hydra template from Pywr.
"""
# TODO import the other domains
from pywr.domains.river import *
from pywr.nodes import NodeMeta, Node, Storage
from pywr.recorders import NumpyArrayNodeRecorder, NumpyArrayStorageRecorder
import pywr
import os
import json
import copy
from .core import data_type_from_field

PYWR_PROTECTED_NODE_KEYS = ('name', 'comment', 'type', 'position')

PYWR_ARRAY_RECORDER_ATTRIBUTES = {
    NumpyArrayNodeRecorder: 'simulated_flow',
    NumpyArrayStorageRecorder: 'simulated_volume'
}

PYWR_OUTPUT_ATTRIBUTES = list(PYWR_ARRAY_RECORDER_ATTRIBUTES.values())
PYWR_TIMESTEPPER_ATTRIBUTES = ('start', 'end', 'timestep')
PYWR_DEFAULT_DATASETS = {
    'start': {'data_type': 'descriptor', 'val': '2018-01-01', 'units': 'date', 'name': 'Default start date'},
    'end': {'data_type': 'descriptor', 'val': '2018-12-31', 'units': 'date', 'name': 'Default end date'},
    'timestep': {'data_type': 'scalar', 'val': 1, 'units': 'days', 'name': 'Default timestep'},
}

CONFIG_DIR = os.path.join(os.path.dirname(__file__), 'template_configs')


def _load_layouts():
    with open(os.path.join(os.path.dirname(__file__), 'node_layouts.json')) as fh:
        return json.load(fh)
PYWR_LAYOUTS = _load_layouts()


def get_layout(node_klass):

    layout = copy.deepcopy(PYWR_LAYOUTS['__default__'])
    try:
        node_specific_layout = PYWR_LAYOUTS[node_klass.__name__.lower()]
    except KeyError:
        node_specific_layout = {}
    layout.update(node_specific_layout)
    return layout


def pywr_template_name(config_name):
    """ The name of the Hydra template for Pywr. """
    return 'Pywr {} template (version: {}, git hash: {})'.format(config_name, pywr.__version__,
                                                                 pywr.__git_hash__[:6])


def generate_pywr_attributes():

    attribute_names = set()

    # First add the attributes for the timestepper section
    for name in PYWR_TIMESTEPPER_ATTRIBUTES:
        if name not in attribute_names:
            yield {
                'name': 'timestepper.{}'.format(name),
                'dimension': 'dimensionless',
                'description': ''
            }

    # Now add the constant attributes defined here.
    for name in PYWR_OUTPUT_ATTRIBUTES:
        if name not in attribute_names:
            yield {
                'name': name,
                'dimension': 'dimensionless',
                'description': ''
            }
            attribute_names.add(name)

    # Now add those from the Pywr schemas
    for node_name, node_klass in NodeMeta.node_registry.items():
        schema = node_klass.Schema()

        for name, field in schema.fields.items():
            if name in PYWR_PROTECTED_NODE_KEYS:
                continue

            if name not in attribute_names:
                yield {
                    'name': name,
                    'dimension': 'dimensionless',
                    'description': ''
                }
                attribute_names.add(name)


def generate_pywr_node_templates(attribute_ids, whitelist=None, blacklist=None):

    for node_name, node_klass in NodeMeta.node_registry.items():
        if node_klass == Node:
            # Don't add the basic abstract node from Pywr.
            continue

        # Skip non-whitelisted or blacklisted nodes
        if whitelist is not None:
            if node_name.lower() not in whitelist:
                continue
        if blacklist is not None:
            if node_name.lower() in blacklist:
                continue

        schema = node_klass.Schema()

        # Create an attribute for each field in the schema.
        type_attributes = []
        for name, field in schema.fields.items():
            if name in PYWR_PROTECTED_NODE_KEYS:
                continue

            data_type = data_type_from_field(field)

            type_attributes.append({
                'attr_id': attribute_ids[name],
                'data_type': data_type,
                'description': '',
            })

        # Create an output attribute for each node
        if issubclass(node_klass, Node):
            output_attribute_name = 'simulated_flow'
        elif issubclass(node_klass, Storage):
            output_attribute_name = 'simulated_volume'
        else:
            output_attribute_name = None

        if output_attribute_name is not None:
            type_attributes.append({
                'attr_id': attribute_ids[output_attribute_name],
                'description': '',
                'data_type': 'dataframe',
                'is_var': 'Y'
            })

        # Now create the layout
        layout = get_layout(node_klass)

        yield {
            'name': node_name,
            'resource_type': 'NODE',
            'typeattrs': type_attributes,
            'layout': layout,
        }


def generate_pywr_template(attribute_ids, default_data_set_ids, config_name):

    config = load_template_config(config_name)

    template_types = [
        {
            'name': 'edge',
            'resource_type': 'LINK',
            'typeattrs': [],
            # Default layout for links
            'layout': {"linestyle": "solid", "width": "7", "color": "#000000", "hidden": "N"}
        },
        {
            'name': 'Pywr {}'.format(config_name.capitalize()),
            'resource_type': 'NETWORK',
            'typeattrs': [
                {
                    'attr_id': attribute_ids['timestepper.{}'.format(name)],
                    'data_type': 'descriptor' if name != 'timestep' else 'scalar',
                    'description': '',
                    'default_dataset_id': default_data_set_ids[name],
                    'is_var': 'N'
                }
                for name in PYWR_TIMESTEPPER_ATTRIBUTES
            ]
        }
    ]

    # Get any white or black listed nodes from the template configuration.
    node_whitelist = config['nodes'].get('whitelist', None)
    if node_whitelist is not None:
        node_whitelist = [n.lower() for n in node_whitelist]
    node_blacklist = config['nodes'].get('blacklist', None)
    if node_blacklist is not None:
        node_blacklist = [n.lower() for n in node_blacklist]
    #
    for t in generate_pywr_node_templates(attribute_ids, whitelist=node_whitelist,
                                          blacklist=node_blacklist):
        template_types.append(t)

    # TODO add layout
    template = {
        'name': pywr_template_name(config['name']),
        'templatetypes': template_types,
    }

    return template


def add_default_datasets(client):

    default_data_set_ids = {}
    for attribute_name, dataset in PYWR_DEFAULT_DATASETS.items():
        hydra_dataset = client.add_dataset(flush=True, **dataset)
        default_data_set_ids[attribute_name] = hydra_dataset['id']
    return default_data_set_ids


def register_template(client, config_name='full'):
    """ Register the template with Hydra. """

    # TODO check to see if the template exists first.
    attributes = [a for a in generate_pywr_attributes()]

    # The response attributes have ids now.
    response_attributes = client.add_attributes(attributes)

    # Now add the default datasets
    default_data_set_ids = add_default_datasets(client)

    # Convert to a simple dict for local processing.
    attribute_ids = {a.name: a.id for a in response_attributes}

    template = generate_pywr_template(attribute_ids, default_data_set_ids, config_name)

    client.add_template(template)


def unregister_template(client, config_name='full'):
    """ Unregister the template with Hydra. """

    config = load_template_config(config_name)
    template = client.get_template_by_name(pywr_template_name(config['name']))
    client.delete_template(template['id'])


def load_template_config(config_name):
    with open(os.path.join(CONFIG_DIR, '{}.json'.format(config_name))) as fh:
        config = json.load(fh)
    return config