from __future__ import annotations

import asyncio.subprocess
import json
from typing import Text, Dict, Tuple

from packaging.requirements import Requirement
from pkg_resources import resource_filename

from .data import Candidate, CandidateInfo, RequirementWrapper


async def nix_hash(candidate: Candidate) -> Tuple[str, str, str]:
	proc = await asyncio.create_subprocess_exec('nix-prefetch-url', '--print-path',
		'--type', candidate.hash_type, candidate.url, candidate.hash,
		stdout=asyncio.subprocess.PIPE)

	stdout = await proc.stdout.read()
	await proc.wait()

	output = stdout.splitlines()
	assert output[0].decode() == candidate.hash
	nix_path = output[1].decode()

	proc = await asyncio.create_subprocess_exec('nix-hash', '--flat', '--base32',
		'--type', 'sha512', nix_path, stdout=asyncio.subprocess.PIPE)
	stdout = await proc.stdout.read()
	await proc.wait()

	output = stdout.splitlines()
	return 'sha512', output[0].decode(), nix_path


async def prefetch(candidate: Candidate) -> Text:
	proc = await asyncio.create_subprocess_exec('nix-prefetch-url', '--print-path',
		'--type', candidate.hash_type, candidate.url, candidate.hash,
		stdout=asyncio.subprocess.PIPE)

	stdout = await proc.stdout.read()
	await proc.wait()

	output = stdout.splitlines()
	return output[1].decode()


async def get_hash(nix_path: Text) -> Tuple[Text, Text]:
	proc = await asyncio.create_subprocess_exec('nix-hash', '--flat', '--base32', '--type',
		'sha512', nix_path, stdout=asyncio.subprocess.PIPE)

	stdout = await proc.stdout.read()
	await proc.wait()

	output = stdout.splitlines()
	return 'sha512', output[0].decode()


async def get_environment(python_version: Text) -> Dict[Text, Text]:
	arguments = (
		'nix-build', '-Q', '--no-out-link', "-A", "environment",
		'--argstr', 'python_version', 'python%s' % python_version,
		resource_filename(__name__, 'nix/package.nix')
	)
	proc = await asyncio.create_subprocess_exec(*arguments, stdout=asyncio.subprocess.PIPE)

	await proc.wait()
	stdout = await proc.stdout.read()

	output = stdout.splitlines()
	filename = output[0].decode()

	with open(filename) as fp:
		return json.load(fp)


async def get_package_dependencies(python_version: Text, candidate: Candidate) -> CandidateInfo:
	arguments = (
		'nix-build', '-Q', '--no-out-link', '-A', 'metadata',
		'--argstr', 'python_version', 'python%s' % python_version,
		'--argstr', 'name', f'{candidate.name}-{candidate.version}',
		'--arg', 'src', '(import <nixpkgs> {}).fetchurl { url = "%(url)s"; %(hash_type)s = "%(hash)s"; }' % {
			'url': candidate.url,
			'hash_type': candidate.hash_type,
			'hash': candidate.hash,
		},
		resource_filename(__name__, 'nix/package.nix')
	)
	proc = await asyncio.create_subprocess_exec(*arguments, stdout=asyncio.subprocess.PIPE)

	await proc.wait()
	stdout = await proc.stdout.read()

	output = stdout.splitlines()
	filename = output[0].decode()

	with open(filename) as fp:
		metadata = json.load(fp)

	req_setup = set(RequirementWrapper.from_requirement(req) for req in metadata['requirements']['setup'])
	req_test = set(RequirementWrapper.from_requirement(req) for req in metadata['requirements']['test'])
	req_install = set(RequirementWrapper.from_requirement(req) for req in metadata['requirements']['install'])

	extras = {
		key: set(RequirementWrapper.from_requirement(req) for req in value)
			for key, value in metadata['requirements']['extras'].items()
	}

	return CandidateInfo(req_setup, req_test, req_install, extras)
