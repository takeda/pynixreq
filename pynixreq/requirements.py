from typing import Dict, List, Set, Tuple

from packaging.requirements import Requirement

from pynixreq.data import Candidate
from . import __version__
from .fetch import Package


req_template = {
	'header': [
		f'# Generated by pynixreq {__version__}\n',
		'{ buildPythonPackage, fetchurl, setup, args }:\n',
		'self: {'
	],
	'footer': [
		'}'
	]
}


def read_requirements(filename: str) -> Tuple[Set[Requirement], Dict[str, str]]:
	config = {}
	requirements = set()
	with open(filename) as fp:
		for line in fp:
			line = line[:line.find('#')].strip()
			if line == '':
				continue

			if line[:2] == '--':
				command, arg = line[2:].split(maxsplit=1)

				if command in ('index-url', 'extra-index-url'):
					config[command] = arg
				else:
					print(f'TODO: parse {line}')
				continue

			requirements.add(Requirement(line))

	return requirements, config


def write_requirements(filename: str, packages: List[Candidate]):
	def format(lines, level=1):
		return map(lambda x: '%s%s\n' % ('\t' * level, x), lines)

	with open(filename, 'w') as fo:
		fo.writelines(format(req_template['header'], 0))

		for package in sorted(packages, key=lambda x: x.name):
			fo.writelines(format(package.to_nix()))

		fo.writelines(format(req_template['footer'], 0))
