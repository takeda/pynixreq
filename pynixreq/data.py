from __future__ import annotations

import re
from dataclasses import dataclass, field, InitVar, replace
from enum import Flag, auto
from functools import reduce
from typing import Dict, Set, Text, Tuple, Type, List, FrozenSet, Optional

from packaging.markers import Marker
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import Version


class DependencyMode(Flag):
	"""types of dependencies"""
	RUN = auto()
	TEST = auto()
	SETUP = auto()


@dataclass
class TargetDetails:
	"""Settings for dependency resolver"""
	python_version: Text
	mode: DependencyMode = DependencyMode.RUN
	pre_release: bool = False  # TODO: probably not needed


@dataclass(frozen=True)
class RequirementWrapper:
	"""Individual requirement as specified in setup.py/setup.cfg/requirements.txt"""
	# req_text: InitVar[Text] = None
	name: Text = field(default=None)
	url: Text = field(default=None)
	extras: FrozenSet[Text] = field(default=None)
	specifier: SpecifierSet = field(default=None)
	marker: Optional[Marker] = field(default=None)
	key: Text = field(init=False)

	@classmethod
	def from_requirement(cls, req_text: Text) -> RequirementWrapper:
		req = Requirement(req_text)
		return RequirementWrapper(req.name, req.url, frozenset(req.extras), req.specifier, req.marker)
		# object.__setattr__(self, 'name', req.name)
		# object.__setattr__(self, 'url', req.url)
		# object.__setattr__(self, 'extras', frozenset(req.extras))
		# object.__setattr__(self, 'specifier', req.specifier)
		# object.__setattr__(self, 'marker', req.marker)

	def __post_init__(self) -> None:
		# if req_text:
		# 	req = Requirement(req_text)
		# 	object.__setattr__(self, 'name', req.name)
		# 	object.__setattr__(self, 'url', req.url)
		# 	object.__setattr__(self, 'extras', frozenset(req.extras))
		# 	object.__setattr__(self, 'specifier', req.specifier)
		# 	object.__setattr__(self, 'marker', req.marker)
		#	# object.__setattr__(self, 'requirement', req)
		object.__setattr__(self, 'key', re.sub(r'[^A-Za-z0-9.]+', '-', self.name).lower())

	def __and__(self, other):
		if not isinstance(other, RequirementWrapper):
			return NotImplemented

		if other.key != self.key:
			return NotImplemented

		if other.url != self.url:
			return NotImplemented

		return replace(self, extras=self.extras | other.extras, specifier=self.specifier & other.specifier, marker=None)

	def __str__(self):
		parts = [self.name]

		if self.extras:
			parts.append("[{0}]".format(",".join(sorted(self.extras))))

		if self.specifier:
			parts.append(str(self.specifier))

		if self.url:
			parts.append("@ {0}".format(self.url))

		if self.marker:
			parts.append("; {0}".format(self.marker))

		return "".join(parts)


@dataclass(frozen=True)
class PackageTuple:
	candidate: Candidate
	requirements: FrozenSet[RequirementWrapper]


@dataclass
class Dependency:
	"""individual dependency"""
	name: Text
	specifiers: Dict[name, Tuple[Version, SpecifierSet]]
	requested_by: Set[Text] = field(default_factory=set, compare=False)
	candidates: Dict[Version, Candidate] = field(default=None, compare=False)
	chosen_version: Version = None

	@classmethod
	def from_requirement(cls, text: Text) -> Dependency:
		requirement = Requirement(text)

		return cls(requirement.name, requirement.specifier)

	@property
	def combined_specifiers(self) -> SpecifierSet:
		return reduce(lambda x, y: x[1] & y[1], self.specifiers.values())

	def add_specifiers(self, name: str, version: Version, specifiers: SpecifierSet) -> None:
		assert name not in self.specifiers
		self.specifiers[name] = (version, specifiers)

	def remove_specifiers(self, name: str) -> None:
		assert name in self.specifiers
		del self.specifiers[name]


# @dataclass(frozen=True)
# class DependencyChange:
# 	package: Text
# 	version: Version
# 	add

@dataclass
class Candidate:
	name: str
	version: Version
	url: str
	hash_type: str
	hash: str
	requires_python: SpecifierSet
	info: CandidateInfo = None

	def to_nix(self):
		return [
			f'"{self.name}" = buildPythonPackage {{',
			f'\tpname = "{self.name}";',
			f'\tversion = "{self.version}";',
			'\tsrc = fetchurl {',
			f'\t\turl = "{self.url}";',
			f'\t\t{self.hash_type} = "{self.hash}";',
			'\t};',
			'};'
		]

	def _is_comparable(self, other):
		return isinstance(other, type(self)) and self.name == other.name

	def __lt__(self, other):
		if not self._is_comparable(other):
			return NotImplemented

		return self.version < other.version

	def __le__(self, other):
		if not self._is_comparable(other):
			return NotImplemented

		return self.version <= other.version

	def __eq__(self, other):
		if not self._is_comparable(other):
			return NotImplemented

		return self.version == other.version

	def __ne__(self, other):
		if not self._is_comparable(other):
			return NotImplemented

		return self.version != other.version

	def __gt__(self, other):
		if not self._is_comparable(other):
			return NotImplemented

		return self.version > other.version

	def __ge__(self, other):
		if not self._is_comparable(other):
			return NotImplemented

		return self.version >= other.version


@dataclass
class CandidateInfo:
	dep_setup: Set[RequirementWrapper]
	dep_test: Set[RequirementWrapper]
	dep_run: Set[RequirementWrapper]
	extras: Dict[Text, Set[RequirementWrapper]]
