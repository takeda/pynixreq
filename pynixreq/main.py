import asyncio
import logging
from argparse import ArgumentParser

from setuptools.config import read_configuration

from pynixreq.data import RequirementWrapper, TargetDetails
from .compile_requirements import DependencySolver
from .requirements import write_requirements


async def async_cli():
	parser = ArgumentParser(description='Generate requirements.nix from dependencies')
	parser.add_argument('--python-target', '-V', required=True, help='Major python version')
	args = parser.parse_args()

	target = TargetDetails(args.python_target)

	requirements = set()
	configuration = read_configuration('setup.cfg')

	for dep in configuration['options'].get('setup_requires', []):
		requirements.add(RequirementWrapper.from_requirement(dep))

	for dep in configuration['options'].get('tests_require', []):
		requirements.add(RequirementWrapper.from_requirement(dep))

	for dep in configuration['options'].get('install_requires', []):
		requirements.add(RequirementWrapper.from_requirement(dep))

	for extra in configuration['options'].get('extras', {}).values():
		for dep in extra:
			requirements.add(RequirementWrapper.from_requirement(dep))

	solver = DependencySolver(requirements, target)
	await solver.run()

	write_requirements('requirements.nix', solver.candidates)


def cli():
	logging.basicConfig(level=logging.DEBUG)
	loop = asyncio.get_event_loop()
	loop.run_until_complete(async_cli())
	# loop.run_until_complete(loop.shutdown_asyncgens())
	# loop.close()
	# return asyncio.run(async_cli(), debug=True)
