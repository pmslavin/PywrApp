""" This simple script is used to generate the Hydra plugin information. """

# Click CLI interface
import click
from xml.etree import ElementTree as ET

ARGTYPES = {
    'network_id': 'network',
    'scenario_id': 'scenario',
    'user_id': 'user'
}


def make_plugins(group, docker_image):
    """ Generator of plugin XML data from the hydra_pywr CLI. """
    for name, command in group.commands.items():

        try:
            hydra_app_category = command.hydra_app_category
        except AttributeError:
            hydra_app_category = False

        if not hydra_app_category:
            continue

        # Create plugin data for each sub-command of the group.
        data = make_plugin(command, hydra_app_category, docker_image)
        # Convert the data to etree ElementTree
        xml = plugin_to_xml(data)
        yield name, xml


def make_plugin(command, category, docker_image):
    """ Make an individual plugin XML definition from a `click.Command`. """

    return {
        'plugin_name': command.short_help,
        'plugin_dir': '',
        'plugin_description': command.help,
        'plugin_category': category,
        'plugin_command': 'hydra-pywr {}'.format(command.name),
        'plugin_shell': 'docker',
        'plugin_docker_image': docker_image,
        'plugin_location': '.',
        'plugin_nativelogextension': '.log',
        'plugin_nativeoutputextension': '.out',
        'smallicon': None,
        'largeicon': None,
        'plugin_epilog': command.epilog,
        'mandatory_args': [arg for arg in make_args(command)],
        'non_mandatory_args': [arg for arg in make_args(command, required=False)],
        'switches': []
    }


def make_args(command, required=True):
    """ Generate argument definitions for each parameter in command. """
    for param in command.params:
        if not isinstance(param, (click.Argument, click.Option)):
            continue

        if param.required != required:
            continue

        arg = {
            'name': param.name,
            'switch': '--' + param.name.replace('_', '-'),
            'multiple': 'Y' if param.multiple else 'N',
        }

        # Add argtype if matches a given type.
        try:
            arg['argtype'] = ARGTYPES[param.name]
        except KeyError:
            pass

        yield arg


def plugin_to_xml(data):
    """ Convert plugin definition to ElementTree. """
    root = ET.Element('plugin_info')

    for key, value in data.items():
        e = ET.SubElement(root, key, )

        if key in ('mandatory_args', 'non_mandatory_args'):
            for arg in value:
                arg_element = ET.SubElement(e, 'arg')
                for arg_key, arg_value in arg.items():
                    arg_sub_element = ET.SubElement(arg_element, arg_key)
                    arg_sub_element.text = arg_value
        else:
            e.text = value

    return root
