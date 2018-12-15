from __future__ import annotations

from logging import getLogger
from typing import Dict, FrozenSet, Generator, Iterable, Iterator, Set, Text

from packaging.version import Version

from . import nix
from .data import Candidate, CandidateInfo, Dependency, DependencyMode, PackageTuple, RequirementWrapper, TargetDetails
from .pypi import PyPI

log = getLogger(__name__)


class DependencySolver:
	def __init__(self, requirements: Iterable[RequirementWrapper], target: TargetDetails) -> None:
		self.starting_requirements = frozenset(requirements)
		self.target = target

		self._requirements: Dict[Text, PackageTuple] = {}

		self.pypi = PyPI({})
		self.environment: Dict[Text, Text] = None

		self._versions: Dict[Text, Dict[Version, Candidate]] = {}
		self._candidates: Dict[Text, Dict[Version, CandidateInfo]] = {}
		self._dependencies: Dict[Text, Dependency] = {}

	async def initialize(self):
		assert self.environment is None
		self.environment = await self._get_environment()
		self.starting_requirements = frozenset(self._evaluate_markers(self.starting_requirements))

	@property
	def requirements(self) -> FrozenSet[RequirementWrapper]:
		assert self.environment is not None
		requirements = {}

		for requirement in self.starting_requirements:
			if requirement.key in requirements:
				requirements[requirement.key] &= requirement
			else:
				requirements[requirement.key] = requirement

		for package_tuple in self._requirements.values():
			for requirement in package_tuple.requirements:
				if not requirement.key in requirements:
					requirements[requirement.key] = requirement
					continue

				requirements[requirement.key] &= requirement

		return frozenset(requirements.values())

	@property
	def candidates(self):
		return [candidate.candidate for candidate in self._requirements.values()]

	async def _get_environment(self) -> Dict[Text, Text]:
		return await nix.get_environment(self.target.python_version)

	def _evaluate_markers(self, requirements: Iterable[RequirementWrapper]) -> Iterator[RequirementWrapper]:
		"""Remove all requirements that don't classify according to markers"""
		assert self.environment is not None
		return (x for x in requirements if not x.marker or x.marker.evaluate(self.environment))

	async def _pick_package_version(self, requirement: RequirementWrapper) -> Generator[Candidate, None, None]:
		candidates = await self.pypi.get_package_versions(requirement.name)

		for candidate in sorted(candidates.values(), reverse=True):
			if not self.target.pre_release and (candidate.version.is_devrelease or candidate.version.is_prerelease):
				continue

			if requirement.specifier.contains(candidate.version):
				yield candidate

	def _get_dependencies(self, requirement: RequirementWrapper, candidate_info: CandidateInfo) -> FrozenSet[RequirementWrapper]:
		new_dependencies = set()  # type: Set[RequirementWrapper]

		if self.target.mode & DependencyMode.SETUP:
			new_dependencies |= candidate_info.dep_setup

		if self.target.mode & DependencyMode.RUN:
			new_dependencies |= candidate_info.dep_run

		if self.target.mode & DependencyMode.TEST:
			new_dependencies |= candidate_info.dep_test

		for extra in requirement.extras:
			if extra not in candidate_info.extras:
				continue

			new_dependencies |= candidate_info.extras[extra]

		return frozenset(self._evaluate_markers(new_dependencies))

	async def run_once(self):
		assert self.environment is not None
		changed = False

		requirements = sorted(self._evaluate_markers(self.requirements), key=lambda x: x.key)

		log.debug("Current constraints:")
		for requirement in requirements:
			selected = self._requirements[requirement.key].candidate.version if requirement.key in self._requirements else 'not selected yet'
			log.debug('  %s [%s]', requirement, selected)

		for requirement in requirements:
			if requirement.key in self._requirements:
				continue

			log.debug('Processing requirement: %s', requirement.name)
			async for candidate in self._pick_package_version(requirement):
				log.debug('Picked version: %s', candidate.version)
				candidate_info = await nix.get_package_dependencies(self.target.python_version, candidate)
				dependencies = self._get_dependencies(requirement, candidate_info)

				self._requirements[requirement.key] = PackageTuple(candidate, dependencies)
				if dependencies:
					log.debug('New dependencies: %s', ", ".join(sorted(map(lambda x: str(x), dependencies))))
					changed = True
				break

		return changed

	async def get_candidate_info(self, candidate: Candidate) -> CandidateInfo:
		"""run setup.py of a candidate to obtain its dependencies"""

		if candidate.info is None:
			if candidate.name not in self._candidates:
				self._candidates[candidate.name] = {}

			if candidate.version not in self._candidates[candidate.name]:
				self._candidates[candidate.name][candidate.version] = await nix.get_package_dependencies(self.target.python_version, candidate)

			candidate.info = self._candidates[candidate.name][candidate.version]

		return candidate.info

	async def run(self):
		await self.initialize()

		run = 0
		while True:
			run += 1
			log.info(f'Run #{run}')
			if not await self.run_once():
				break
